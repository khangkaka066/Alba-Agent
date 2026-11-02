"""Tenant-scoped capsule governance and transfer-impact telemetry API."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select

from app.auth.context import TenantContext, require_role
from app.models import AuditLog, KnowledgeCapsule, LearningPolicy, TransferApplicationLog, TransferCircuitBreaker
from app.models.scope import scoped_session
from app.learning import save_capsule
from app.routers.common import get_services
from learning_transfer.negative_transfer_detector import DetectorConfig, TransferObservation, score_transfer_pair
from nexus_core_schema.models import KnowledgeCapsuleSpec, PropagationScope, RuntimeEventType, SensitivityLevel, TransferTelemetrySpec
from callbacks.event_bus import RuntimeEventEmitter

router = APIRouter(prefix="/api/v1/learning-transfer", tags=["learning transfer"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_agent_id: str = Field(min_length=1, max_length=100)
    target_agent_id: str = Field(min_length=1, max_length=100)
    propagation_scope: PropagationScope
    allow_heuristics: bool = True
    allow_code_patterns: bool = False
    require_human_approval: bool = False
    allowed: bool = True
    source_domain_tags: list[str] = Field(default_factory=list, max_length=100)
    target_domain_tags: list[str] = Field(default_factory=list, max_length=100)


@router.post("/capsules", status_code=status.HTTP_201_CREATED)
async def create_capsule(request: Request, body: KnowledgeCapsuleSpec, context: BUILD) -> KnowledgeCapsuleSpec:
    if (body.tenant_id, body.workspace_id) != (context.tenant_id, context.workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Capsule scope differs from authenticated workspace")
    await save_capsule(get_services(request), body)
    return body


@router.get("/capsules")
async def list_capsules(request: Request, context: READ) -> list[KnowledgeCapsuleSpec]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(KnowledgeCapsule).where(KnowledgeCapsule.status == "active").order_by(KnowledgeCapsule.created_at.desc()).limit(500))).all()
        return [KnowledgeCapsuleSpec(
            tenant_id=row.tenant_id, workspace_id=row.workspace_id, capsule_id=row.capsule_id,
            source_agent_id=row.source_agent_id, source_role=row.source_role, source_domain_tags=tuple(row.source_domain_tags),
            trigger_preconditions=row.trigger_preconditions, distilled_heuristic=row.distilled_heuristic,
            prohibited_contexts=tuple(row.prohibited_contexts), propagation_scope=PropagationScope(row.propagation_scope),
            sensitivity_level=SensitivityLevel(row.sensitivity_level), source_workflow_id=row.source_workflow_id,
            source_crew_id=row.source_crew_id, confidence=row.confidence,
        ) for row in rows]


@router.get("/policies")
async def list_policies(request: Request, context: READ) -> list[dict[str, Any]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(LearningPolicy).order_by(LearningPolicy.source_agent_id, LearningPolicy.target_agent_id))).all()
        return [{"id": str(row.id), "source_agent_id": row.source_agent_id, "target_agent_id": row.target_agent_id,
                 "propagation_scope": row.propagation_scope, "allow_heuristics": row.allow_heuristics,
                 "allow_code_patterns": row.allow_code_patterns, "require_human_approval": row.require_human_approval,
                 "allowed": row.allowed, "source_domain_tags": row.source_domain_tags, "target_domain_tags": row.target_domain_tags} for row in rows]


@router.put("/policies")
async def upsert_policy(request: Request, body: PolicyInput, context: BUILD) -> dict[str, Any]:
    if body.source_agent_id == body.target_agent_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A learning edge must connect distinct agents")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(LearningPolicy).where(
            LearningPolicy.source_agent_id == body.source_agent_id,
            LearningPolicy.target_agent_id == body.target_agent_id,
        ).with_for_update())
        values = {
            "propagation_scope": _enum_value(body.propagation_scope),
            "allow_heuristics": body.allow_heuristics,
            "allow_code_patterns": body.allow_code_patterns,
            "require_human_approval": body.require_human_approval,
            "allowed": body.allowed,
            "source_domain_tags": body.source_domain_tags,
            "target_domain_tags": body.target_domain_tags,
        }
        if row is None:
            row = LearningPolicy(id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                 source_agent_id=body.source_agent_id, target_agent_id=body.target_agent_id, **values)
            session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
    return {"source_agent_id": body.source_agent_id, "target_agent_id": body.target_agent_id, **values}


@router.post("/capsules/{capsule_id}/targets/{target_agent_id}/restore")
async def restore_transfer_pair(
    capsule_id: UUID, target_agent_id: str, request: Request, context: BUILD,
) -> dict[str, Any]:
    """Roll back one target quarantine without changing other target pairs."""
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        capsule = await session.scalar(select(KnowledgeCapsule).where(
            KnowledgeCapsule.capsule_id == capsule_id,
        ).with_for_update())
        if capsule is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Capsule is not visible in this workspace")
        breaker = await session.scalar(select(TransferCircuitBreaker).where(
            TransferCircuitBreaker.capsule_id == capsule.id,
            TransferCircuitBreaker.target_agent_id == target_agent_id,
        ).with_for_update())
        if breaker is None or not breaker.active:
            raise HTTPException(status.HTTP_409_CONFLICT, "No active quarantine exists for this target")
        policy = await session.scalar(select(LearningPolicy).where(
            LearningPolicy.source_agent_id == capsule.source_agent_id,
            LearningPolicy.target_agent_id == target_agent_id,
        ).with_for_update())
        if policy is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Propagation policy no longer exists")
        breaker.active = False
        policy.allowed = True
        other_breakers = (await session.scalars(select(TransferCircuitBreaker).where(
            TransferCircuitBreaker.capsule_id == capsule.id,
            TransferCircuitBreaker.target_agent_id != target_agent_id,
            TransferCircuitBreaker.active.is_(True),
        ))).all()
        still_prohibited = {value for item in other_breakers for value in item.target_domain_tags}
        remove_values = set(breaker.target_domain_tags) - still_prohibited
        remove_values.add(target_agent_id)
        capsule.prohibited_contexts = [value for value in capsule.prohibited_contexts if value not in remove_values]
        session.add(AuditLog(
            id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            actor_id=context.user_id, action="learning_transfer.quarantine_rolled_back",
            target_type="knowledge_capsule", target_id=capsule.id,
            details={"target_agent_id": target_agent_id, "previous_tis_score": breaker.tis_score},
        ))
    return {"capsule_id": str(capsule_id), "target_agent_id": target_agent_id,
            "restored": True, "policy_scope": policy.propagation_scope}


@router.post("/telemetry")
async def record_transfer_telemetry(request: Request, body: TransferTelemetrySpec, context: BUILD) -> dict[str, Any]:
    if (body.tenant_id, body.workspace_id) != (context.tenant_id, context.workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Telemetry scope differs from authenticated workspace")
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        capsule = await session.scalar(select(KnowledgeCapsule).where(KnowledgeCapsule.capsule_id == body.capsule_id).with_for_update())
        if capsule is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Capsule is not visible in this workspace")
        breaker = await session.scalar(select(TransferCircuitBreaker).where(
            TransferCircuitBreaker.capsule_id == capsule.id,
            TransferCircuitBreaker.target_agent_id == body.target_agent_id,
            TransferCircuitBreaker.active.is_(True),
        ).with_for_update())
        if breaker is not None and body.condition == "treatment":
            raise HTTPException(status.HTTP_409_CONFLICT, "Transfer is quarantined for this target agent")
        log_row = TransferApplicationLog(
            id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            capsule_id=capsule.id, run_id=body.run_id, source_agent_id=body.source_agent_id,
            target_agent_id=body.target_agent_id, condition=body.condition, success=body.success,
            retry_and_error_turns=body.retry_and_error_turns,
            human_approval_rejected=body.human_approval_rejected, token_count=body.token_count,
            latency_ms=body.latency_ms, target_domain_tags=list(body.target_domain_tags),
        )
        session.add(log_row)
        logs = (await session.scalars(select(TransferApplicationLog).where(
            TransferApplicationLog.capsule_id == capsule.id,
            TransferApplicationLog.target_agent_id == body.target_agent_id,
        ))).all()
        def to_observation(item: TransferApplicationLog) -> TransferObservation:
            return TransferObservation(
                success=item.success, retry_and_error_turns=item.retry_and_error_turns,
                human_approval_rejected=item.human_approval_rejected, token_count=item.token_count,
                latency_ms=item.latency_ms,
            )
        baseline = tuple(to_observation(item) for item in logs if item.condition == "baseline")
        treatment = tuple(to_observation(item) for item in logs if item.condition == "treatment")
        # Query autoflush includes this newly inserted observation exactly once.
        decision = score_transfer_pair(body.capsule_id, body.target_agent_id, baseline, treatment, DetectorConfig(
            threshold=float(__import__("os").environ.get("NEXUS_TRANSFER_NEGATIVE_THRESHOLD", "0.15")),
            minimum_applications=int(__import__("os").environ.get("NEXUS_TRANSFER_MIN_APPLICATIONS", "5")),
        ))
        log_row.tis_score = decision.impact.score
        if decision.negative_transfer:
            if breaker is None:
                session.add(TransferCircuitBreaker(
                    id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                    capsule_id=capsule.id, target_agent_id=body.target_agent_id,
                    target_domain_tags=list(body.target_domain_tags), tis_score=decision.impact.score,
                    application_count=decision.sample_count, active=True,
                ))
            else:
                breaker.tis_score = decision.impact.score
                breaker.application_count = decision.sample_count
                breaker.target_domain_tags = list(body.target_domain_tags)
            capsule.prohibited_contexts = list(dict.fromkeys([*capsule.prohibited_contexts, body.target_agent_id, *body.target_domain_tags]))
            policy = await session.scalar(select(LearningPolicy).where(
                LearningPolicy.source_agent_id == body.source_agent_id,
                LearningPolicy.target_agent_id == body.target_agent_id,
            ).with_for_update())
            if policy is not None:
                policy.allowed = False
            session.add(AuditLog(
                id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                actor_id=context.user_id, action="learning_transfer.negative_transfer_quarantined",
                target_type="knowledge_capsule", target_id=capsule.id,
                details={"target_agent_id": body.target_agent_id, "tis_score": decision.impact.score,
                         "sample_count": decision.sample_count, "target_domain_tags": list(body.target_domain_tags)},
            ))
    if decision.negative_transfer:
        emitter = RuntimeEventEmitter(services.redis, context.tenant_id, context.workspace_id, body.run_id)
        await emitter.emit(RuntimeEventType.NEGATIVE_TRANSFER_DETECTED, {
            "capsule_id": str(body.capsule_id), "source_agent_id": body.source_agent_id,
            "target_agent_id": body.target_agent_id, "tis_score": decision.impact.score,
            "sample_count": decision.sample_count,
        })
    return {"capsule_id": str(body.capsule_id), "target_agent_id": body.target_agent_id,
            "sample_count": decision.sample_count, "tis_score": decision.impact.score,
            "negative_transfer": decision.negative_transfer, "quarantined": decision.quarantined}


@router.get("/telemetry")
async def transfer_telemetry(request: Request, context: READ) -> dict[str, Any]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.execute(select(
            TransferApplicationLog.capsule_id, TransferApplicationLog.source_agent_id,
            TransferApplicationLog.target_agent_id, TransferApplicationLog.condition,
            func.count(), func.avg(case((TransferApplicationLog.success.is_(True), 1.0), else_=0.0)),
            func.avg(TransferApplicationLog.retry_and_error_turns),
            func.avg(case((TransferApplicationLog.human_approval_rejected.is_(True), 1.0), else_=0.0)),
            func.avg(TransferApplicationLog.token_count), func.avg(TransferApplicationLog.latency_ms),
            func.avg(TransferApplicationLog.tis_score),
        ).group_by(TransferApplicationLog.capsule_id, TransferApplicationLog.source_agent_id,
                   TransferApplicationLog.target_agent_id, TransferApplicationLog.condition))).all()
        breakers = (await session.scalars(select(TransferCircuitBreaker).where(TransferCircuitBreaker.active.is_(True)))).all()
        policy_count = await session.scalar(select(func.count()).select_from(LearningPolicy))
    grouped: dict[tuple[UUID, str, str], dict[str, Any]] = {}
    for capsule_id, source, target, condition, count, success, retries, rejected, tokens, latency, tis in rows:
        item = grouped.setdefault((capsule_id, source, target), {"capsule_id": str(capsule_id), "source_agent_id": source,
                                                                  "target_agent_id": target, "baseline": None, "treatment": None})
        item[condition] = {"applications": int(count), "task_success_rate": float(success or 0),
                           "retry_and_error_turns": float(retries or 0),
                           "human_approval_rejection_rate": float(rejected or 0),
                           "average_tokens": float(tokens or 0), "average_latency_ms": float(latency or 0),
                           "tis_score": float(tis or 0)}
    positive_pairs = sum(1 for item in grouped.values() if (item["treatment"] or {}).get("tis_score", 0) > 0)
    observed_pairs = len(grouped)
    return {"transfer_matrix": list(grouped.values()),
            "positive_transfer_pairs": positive_pairs,
            "negative_transfer_pairs": len(breakers),
            "positive_transfer_rate": positive_pairs / observed_pairs if observed_pairs else 0.0,
            "negative_transfer_rate": len(breakers) / observed_pairs if observed_pairs else 0.0,
            "configured_policy_edges": int(policy_count or 0),
            "auto_quarantined": [{"capsule_id": str(item.capsule_id), "target_agent_id": item.target_agent_id,
                                  "tis_score": item.tis_score, "application_count": item.application_count,
                                  "target_domain_tags": item.target_domain_tags} for item in breakers]}
