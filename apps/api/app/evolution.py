"""Persistence, governance and scoring for evolving team topologies (generations, proposals, rollback)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.context import TenantContext
from app.models import (
    ApprovalRequest,
    AuditLog,
    ModelCredential,
    PromptPatchProposal,
    RunCheckpoint,
    TokenUsageLog,
    TransferApplicationLog,
    Workflow,
    WorkflowEvolutionPolicy,
    WorkflowRun,
    WorkflowTopologyVersion,
)
from app.models.scope import scoped_session
from app.routers.common import conflict, not_found
from nexus_builtin_tools import TOOLS
from nexus_core_schema.models import AutoGenSandboxNodeSpec, CrewNodeSpec, WorkflowSpec
from team_evolution import (
    DYNAMIC_TEAM_TOOL_ID,
    BottleneckAnalyzer,
    FitnessTracker,
    GenerationStats,
    HumanFeedback,
    MutationError,
    MutationOp,
    RunMetrics,
    RunObservation,
    TeamTopologyMutator,
    aggregate,
    extract_run_metrics,
    plan_operations,
    product_fitness,
)
from team_evolution.fitness_tracker import efficiency, quality_score
from pydantic import TypeAdapter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services import AppServices

logger = logging.getLogger("nexus.evolution")

POLICIES = ("SUGGEST_FIRST", "FULLY_AUTONOMOUS")
MAX_GENERATIONS = 12
RUNS_PER_ANALYSIS = 3
FINISHED = ("completed", "failed")
OPERATIONS = TypeAdapter(list[MutationOp])


@dataclass(frozen=True)
class Scope:
    tenant_id: UUID
    workspace_id: UUID
    actor_id: UUID | None = None

    @property
    def context(self) -> TenantContext:
        return TenantContext(self.tenant_id, self.workspace_id, self.actor_id or UUID(int=0), "admin")


# --- lineage ----------------------------------------------------------------------------------------------------

async def ensure_lineage(session: AsyncSession, scope: Scope, workflow_id: UUID, *, create: bool = True) -> tuple[WorkflowEvolutionPolicy, list[WorkflowTopologyVersion]]:
    """Find (or lazily start) the lineage a workflow row belongs to and return its policy and all generations."""
    row = await session.scalar(select(WorkflowTopologyVersion).where(WorkflowTopologyVersion.workflow_id == workflow_id))
    if row is None:
        if not create:
            raise LookupError("This workflow has not started evolving")
        workflow = await session.get(Workflow, workflow_id)
        if workflow is None:
            raise not_found("Workflow is not visible in this workspace")
        row = WorkflowTopologyVersion(
            tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, lineage_id=workflow.id, workflow_id=workflow.id,
            version_number=workflow.version, parent_version=None, status="active", origin="baseline", spec=workflow.spec,
            evolution_rationale="Original team topology.", decided_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.add(WorkflowEvolutionPolicy(
            tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, lineage_id=workflow.id,
            auto_evolve_policy="SUGGEST_FIRST", active_workflow_id=workflow.id, active_version=workflow.version,
        ))
        await session.flush()
    policy = await session.scalar(select(WorkflowEvolutionPolicy).where(WorkflowEvolutionPolicy.lineage_id == row.lineage_id))
    if policy is None:
        raise conflict("Lineage has no evolution policy")
    versions = list((await session.scalars(
        select(WorkflowTopologyVersion).where(WorkflowTopologyVersion.lineage_id == row.lineage_id).order_by(WorkflowTopologyVersion.version_number)
    )).all())
    return policy, versions


def _active(policy: WorkflowEvolutionPolicy, versions: list[WorkflowTopologyVersion]) -> WorkflowTopologyVersion:
    return next(item for item in versions if item.workflow_id == policy.active_workflow_id)


# --- measurement ------------------------------------------------------------------------------------------------

async def _run_metrics(session: AsyncSession, spec: WorkflowSpec, run: WorkflowRun) -> RunMetrics:
    checkpoint = await session.scalar(
        select(RunCheckpoint).where(RunCheckpoint.run_id == run.id).order_by(RunCheckpoint.sequence.desc()).limit(1)
    )
    state: dict[str, Any] = dict(checkpoint.state) if checkpoint is not None else {}
    approvals = list((await session.scalars(
        select(ApprovalRequest.status).where(ApprovalRequest.run_id == run.id, ApprovalRequest.status != "pending")
    )).all())
    cost = await session.scalar(select(func.coalesce(func.sum(TokenUsageLog.total_cost_usd), 0)).where(TokenUsageLog.run_id == run.id))
    seconds = (run.finished_at - run.started_at).total_seconds() if run.finished_at and run.started_at else 0.0
    return extract_run_metrics(
        spec, run.status, state.get("node_outputs", {}), state.get("completed_nodes", []), approvals, float(cost or 0), seconds,
    )


def stats_from_row(row: WorkflowTopologyVersion) -> GenerationStats | None:
    if not row.runs_observed or row.artifact_completeness_rate is None or row.product_quality_score is None:
        return None
    return GenerationStats(
        runs=row.runs_observed, artifact_completeness=row.artifact_completeness_rate, quality=row.product_quality_score,
        human_rating=None, cost_usd=float(row.avg_cost_usd or 0), latency_seconds=row.avg_latency_seconds or 0.0,
    )


async def refresh_metrics(session: AsyncSession, versions: list[WorkflowTopologyVersion]) -> None:
    """Recompute every materialised generation's aggregates and fitness from its finished runs."""
    root = next((item for item in versions if item.parent_version is None), versions[0])
    for row in sorted(versions, key=lambda item: item.version_number != root.version_number):
        if row.status == "proposed":
            continue
        spec = WorkflowSpec.model_validate(row.spec)
        runs = list((await session.scalars(
            select(WorkflowRun).where(WorkflowRun.workflow_id == row.workflow_id, WorkflowRun.status.in_(FINISHED))
        )).all())
        stats = aggregate([await _run_metrics(session, spec, run) for run in runs])
        if stats is None:
            continue
        reference = stats_from_row(root) if row is not root else stats
        row.runs_observed = stats.runs
        row.artifact_completeness_rate = stats.artifact_completeness
        row.avg_human_rating = stats.human_rating
        row.product_quality_score = quality_score(stats)
        row.avg_cost_usd = Decimal(str(round(stats.cost_usd, 8)))
        row.avg_latency_seconds = stats.latency_seconds
        row.efficiency = efficiency(stats, reference)
        stored = GenerationStats(stats.runs, stats.artifact_completeness, row.product_quality_score, None, stats.cost_usd, stats.latency_seconds)
        row.fitness = product_fitness(stored, reference)


async def build_observations(session: AsyncSession, spec: WorkflowSpec, runs: list[WorkflowRun]) -> list[RunObservation]:
    agent_node = {agent.id: node.id for node in spec.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents}
    agent_node.update({f"{node.id}_coder": node.id for node in spec.nodes if isinstance(node, AutoGenSandboxNodeSpec)})
    observations: list[RunObservation] = []
    for run in runs:
        checkpoints = list((await session.scalars(
            select(RunCheckpoint).where(RunCheckpoint.run_id == run.id).order_by(RunCheckpoint.sequence)
        )).all())
        state: dict[str, Any] = dict(checkpoints[-1].state) if checkpoints else {}
        seconds: dict[str, float] = {}
        seen: set[str] = set()
        previous = checkpoints[0].created_at if checkpoints else None
        for checkpoint in checkpoints:
            for node_id in list(cast(list[str], checkpoint.state.get("completed_nodes", []))):
                if node_id not in seen and previous is not None:
                    seen.add(node_id)
                    seconds[node_id] = max(0.0, (checkpoint.created_at - previous).total_seconds())
            previous = checkpoint.created_at
        usage = (await session.execute(
            select(TokenUsageLog.agent_name, func.sum(TokenUsageLog.total_cost_usd)).where(TokenUsageLog.run_id == run.id).group_by(TokenUsageLog.agent_name)
        )).all()
        node_cost: dict[str, float] = {}
        for agent_name, total in usage:
            owner = agent_node.get(str(agent_name))
            if owner:
                node_cost[owner] = node_cost.get(owner, 0.0) + float(total or 0)
        denied = list((await session.scalars(
            select(ApprovalRequest).where(ApprovalRequest.run_id == run.id, ApprovalRequest.status == "denied")
        )).all())
        proposals = list((await session.scalars(select(PromptPatchProposal).where(
            PromptPatchProposal.workflow_id == run.workflow_id, PromptPatchProposal.source_approval_id.in_([item.id for item in denied] or [uuid4()]),
        ))).all())
        feedback = [HumanFeedback(node_id=agent_node.get(item.agent_id), decision="edited", comment=item.reviewer_comment) for item in proposals]
        feedback += [HumanFeedback(node_id=None, decision="denied", comment=item.rationale or item.action) for item in denied if not proposals]
        failure = await session.scalar(
            select(AuditLog.details).where(AuditLog.target_id == run.id, AuditLog.action == "workflow.failed").order_by(AuditLog.created_at.desc()).limit(1)
        )
        total_seconds = (run.finished_at - run.started_at).total_seconds() if run.finished_at and run.started_at else None
        observations.append(RunObservation(
            run_id=str(run.id), status=run.status,  # type: ignore[arg-type]
            node_outputs=dict(state.get("node_outputs", {})), completed_nodes=tuple(state.get("completed_nodes", ())),
            node_seconds=seconds, node_cost_usd=node_cost, run_seconds=total_seconds, total_cost_usd=sum(node_cost.values()) or None,
            failure_message=str(failure.get("message")) if isinstance(failure, dict) and failure.get("message") else None,
            human_feedback=tuple(feedback),
        ))
    return observations


async def transfer_scores(session: AsyncSession, spec: WorkflowSpec) -> dict[str, float]:
    agents = {agent.id for node in spec.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents}
    if not agents:
        return {}
    rows = (await session.execute(
        select(TransferApplicationLog.target_agent_id, func.avg(TransferApplicationLog.tis_score))
        .where(TransferApplicationLog.target_agent_id.in_(agents), TransferApplicationLog.tis_score.is_not(None))
        .group_by(TransferApplicationLog.target_agent_id)
    )).all()
    return {str(agent): float(score) for agent, score in rows if score is not None}


# --- serialisation ----------------------------------------------------------------------------------------------

def version_summary(row: WorkflowTopologyVersion, policy: WorkflowEvolutionPolicy) -> dict[str, Any]:
    return {
        "version": row.version_number, "parent_version": row.parent_version, "workflow_id": str(row.workflow_id),
        "status": row.status, "origin": row.origin, "is_active": row.workflow_id == policy.active_workflow_id,
        "mutation_ops_applied": row.mutation_ops_applied, "evolution_rationale": row.evolution_rationale,
        "diagnoses": row.diagnoses, "diff": row.diff, "created_at": row.created_at.isoformat() if row.created_at else None,
        "product_quality_score": row.product_quality_score, "artifact_completeness_rate": row.artifact_completeness_rate,
        "avg_human_rating": row.avg_human_rating, "avg_cost_usd": float(row.avg_cost_usd) if row.avg_cost_usd is not None else None,
        "avg_latency_seconds": row.avg_latency_seconds, "efficiency": row.efficiency, "fitness": row.fitness,
        "runs_observed": row.runs_observed, "decision_note": row.decision_note,
    }


def lineage_view(policy: WorkflowEvolutionPolicy, versions: list[WorkflowTopologyVersion]) -> dict[str, Any]:
    ordered = sorted(versions, key=lambda item: item.version_number)
    return {
        "lineage_id": str(policy.lineage_id), "auto_evolve_policy": policy.auto_evolve_policy,
        "active_workflow_id": str(policy.active_workflow_id), "active_version": policy.active_version,
        "generations": [version_summary(row, policy) for row in ordered],
        "trend": [{"version": row.version_number, "fitness": row.fitness} for row in ordered if row.fitness is not None],
        "lineage": " → ".join(f"v{row.version_number}" for row in ordered if row.status != "rejected"),
    }


# --- governance -------------------------------------------------------------------------------------------------

async def _next_version(session: AsyncSession, scope: Scope, name: str, versions: list[WorkflowTopologyVersion]) -> int:
    latest = await session.scalar(select(func.max(Workflow.version)).where(Workflow.name == name))
    return max(int(latest or 0), *(row.version_number for row in versions)) + 1


async def _materialise(session: AsyncSession, scope: Scope, row: WorkflowTopologyVersion) -> WorkflowSpec:
    from app.routers.workflows import _sync_learning_policies

    spec = WorkflowSpec.model_validate(row.spec)
    if await session.get(Workflow, row.workflow_id) is None:
        session.add(Workflow(
            id=spec.id, tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, name=spec.name, version=spec.version,
            spec=spec.model_dump(mode="json"),
        ))
        try:
            await session.flush()
        except IntegrityError as error:
            raise conflict("A workflow with this name and version already exists") from error
        await _sync_learning_policies(session, spec, scope.context)
    return spec


def _audit(session: AsyncSession, scope: Scope, action: str, row: WorkflowTopologyVersion, details: dict[str, Any]) -> None:
    session.add(AuditLog(
        tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, actor_id=scope.actor_id, action=action,
        target_type="workflow_topology_version", target_id=row.id, details={"lineage_id": str(row.lineage_id), "version": row.version_number, **details},
    ))


async def promote(session: AsyncSession, scope: Scope, policy: WorkflowEvolutionPolicy, versions: list[WorkflowTopologyVersion],
                  row: WorkflowTopologyVersion, note: str | None = None) -> None:
    if row.status not in ("proposed", "rolled_back", "superseded"):
        raise conflict(f"Generation v{row.version_number} is already {row.status}")
    await _materialise(session, scope, row)
    for other in versions:
        if other.status == "active" and other is not row:
            other.status = "superseded"
    row.status, row.decided_at, row.decision_note = "active", datetime.now(timezone.utc), note
    policy.active_workflow_id, policy.active_version = row.workflow_id, row.version_number
    _audit(session, scope, "workflow.topology_promoted", row, {"note": note or ""})


async def rollback_to(session: AsyncSession, scope: Scope, policy: WorkflowEvolutionPolicy, versions: list[WorkflowTopologyVersion],
                      target: WorkflowTopologyVersion, reason: str) -> None:
    if target.status == "proposed":
        raise conflict("A proposal has never been active; approve it or reject it instead")
    await _materialise(session, scope, target)
    for other in versions:
        if other.status == "active" and other is not target:
            other.status, other.decision_note, other.decided_at = "rolled_back", reason, datetime.now(timezone.utc)
    target.status, target.decided_at, target.decision_note = "active", datetime.now(timezone.utc), f"Restored: {reason}"
    policy.active_workflow_id, policy.active_version = target.workflow_id, target.version_number
    _audit(session, scope, "workflow.topology_rolled_back", target, {"reason": reason})


def _signature(operations: list[dict[str, Any]]) -> frozenset[tuple[str, str, str]]:
    return frozenset((str(item.get("op")), str(item.get("target_node_id")), str(item.get("agent_id") or item.get("role") or "")) for item in operations)


# --- evolve -----------------------------------------------------------------------------------------------------

async def _available(session: AsyncSession, services: AppServices, spec: WorkflowSpec) -> tuple[set[str], tuple[str, ...]]:
    from app.routers.architect import _approved_chat_models

    names = {f"{provider}/{model}" for provider, model in services.model_rates}
    for credential in (await session.scalars(select(ModelCredential).where(ModelCredential.status == "connected"))).all():
        names.update(f"{credential.provider}/{model}" for model in credential.available_models)
    names.update(agent.model for node in spec.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents)
    tools = {item.id for item in TOOLS} | {DYNAMIC_TEAM_TOOL_ID}
    return tools, _approved_chat_models(names) or tuple(sorted(names))


async def evolve(
    services: AppServices, scope: Scope, workflow_id: UUID, *, origin: str = "post_run", operations: list[dict[str, Any]] | None = None,
    run_ids: list[UUID] | None = None, auto: bool = False, rationale: str = "",
) -> dict[str, Any]:
    """Analyse the active generation's recent runs and create the next generation (proposal or promotion)."""
    async with scoped_session(services.engine, scope.tenant_id, scope.workspace_id) as session:
        policy, versions = await ensure_lineage(session, scope, workflow_id)
        active = _active(policy, versions)
        if not auto and any(row.status == "proposed" for row in versions) and operations is None:
            pending = next(row for row in versions if row.status == "proposed")
            return {"status": "pending_proposal", "message": f"Generation v{pending.version_number} is waiting for a decision.", **lineage_view(policy, versions)}
        if len([row for row in versions if row.status != "rejected"]) >= MAX_GENERATIONS:
            raise conflict(f"This lineage already has {MAX_GENERATIONS} generations; roll back or reject before evolving again")
        await refresh_metrics(session, versions)
        spec = WorkflowSpec.model_validate(active.spec)
        statement = select(WorkflowRun).where(WorkflowRun.workflow_id == active.workflow_id, WorkflowRun.status.in_(FINISHED))
        if run_ids:
            statement = statement.where(WorkflowRun.id.in_(run_ids))
        runs = list((await session.scalars(statement.order_by(WorkflowRun.created_at.desc()).limit(RUNS_PER_ANALYSIS))).all())
        if not runs and operations is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Run this workflow at least once before evolving its team")
        observations = await build_observations(session, spec, runs)
        scores = await transfer_scores(session, spec)
        tools, models = await _available(session, services, spec)
        next_version = await _next_version(session, scope, spec.name, versions)
        rolled_back = [_signature([cast(dict[str, Any], entry["request"]) for entry in row.mutation_ops_applied if "request" in entry]) for row in versions if row.status == "rolled_back"]

    report = BottleneckAnalyzer().analyze(spec, observations, scores)
    delegated: list[Any] = []
    if operations is not None:
        planned: list[MutationOp] = OPERATIONS.validate_python(operations)
        strict = True
    else:
        plan = plan_operations(report, spec, available_tools=tools, available_models=models)
        planned, delegated, strict = plan.operations, plan.delegated, False
        rationale = rationale or plan.rationale
    if not planned:
        return {"status": "no_change", "message": "No structural change is justified by the recent runs.", "diagnoses": [d.model_dump(mode="json") for d in report.diagnoses],
                "delegated": [d.model_dump(mode="json") for d in delegated]}
    new_id = uuid4()
    try:
        result = TeamTopologyMutator(tools, models).apply(spec, planned, next_version=next_version, new_id=new_id, strict=strict)
    except MutationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    applied = [item.model_dump(mode="json") for item in result.applied]
    plan_signature = _signature([item["request"] for item in applied])
    if auto and any(plan_signature == earlier for earlier in rolled_back):
        return {"status": "no_change", "message": "The same structural change was already rolled back; not repeating it.",
                "diagnoses": [d.model_dump(mode="json") for d in report.diagnoses]}
    promote_now = policy.auto_evolve_policy == "FULLY_AUTONOMOUS"
    async with scoped_session(services.engine, scope.tenant_id, scope.workspace_id) as session:
        policy, versions = await ensure_lineage(session, scope, workflow_id)
        row = WorkflowTopologyVersion(
            tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, lineage_id=policy.lineage_id, workflow_id=new_id,
            version_number=result.spec.version, parent_version=active.version_number, status="proposed",
            origin="autonomous" if auto else origin, spec=result.spec.model_dump(mode="json"),
            mutation_ops_applied=applied,
            evolution_rationale=rationale or " ".join(item["summary"] + "." for item in applied),
            diagnoses=[d.model_dump(mode="json") for d in report.diagnoses], diff=result.diff.model_dump(mode="json"),
        )
        session.add(row)
        await session.flush()
        versions.append(row)
        _audit(session, scope, "workflow.topology_proposed", row, {"operations": [item["op"] for item in applied], "auto": auto})
        if promote_now:
            await promote(session, scope, policy, versions, row, "Promoted automatically (FULLY_AUTONOMOUS)")
        view = lineage_view(policy, versions)
        summary = version_summary(row, policy)
    return {
        "status": "promoted" if promote_now else "proposed", "workflow_id": str(new_id), "version": summary["version"], "generation": summary,
        "applied": applied, "skipped": result.skipped, "diff": result.diff.model_dump(mode="json"), "diff_lines": result.diff.lines(),
        "diagnoses": [d.model_dump(mode="json") for d in report.diagnoses], "delegated": [d.model_dump(mode="json") for d in delegated],
        "lineage": view,
    }


async def record_mid_run_proposal(services: AppServices, scope: Scope, parent_workflow_id: UUID, evolved: WorkflowSpec, note: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist a specialist a director added during a run as a new generation (respecting the governance mode)."""
    async with scoped_session(services.engine, scope.tenant_id, scope.workspace_id) as session:
        policy, versions = await ensure_lineage(session, scope, parent_workflow_id)
        parent = next(row for row in versions if row.workflow_id == parent_workflow_id)
        version = await _next_version(session, scope, evolved.name, versions)
        spec = WorkflowSpec.model_validate({**evolved.model_dump(mode="json"), "version": version})
        from team_evolution import diff_specs

        row = WorkflowTopologyVersion(
            tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, lineage_id=policy.lineage_id, workflow_id=spec.id,
            version_number=version, parent_version=parent.version_number, status="proposed", origin="mid_run",
            spec=spec.model_dump(mode="json"), mutation_ops_applied=operations, evolution_rationale=note,
            diff=diff_specs(WorkflowSpec.model_validate(parent.spec), spec).model_dump(mode="json"),
        )
        session.add(row)
        await session.flush()
        versions.append(row)
        _audit(session, scope, "workflow.topology_proposed", row, {"origin": "mid_run"})
        promoted = policy.auto_evolve_policy == "FULLY_AUTONOMOUS" and parent.workflow_id == policy.active_workflow_id
        if promoted:
            await promote(session, scope, policy, versions, row, "Promoted automatically (FULLY_AUTONOMOUS, spawned mid-run)")
        return {"version": version, "workflow_id": str(spec.id), "status": "active" if promoted else "proposed"}


# --- after a run --------------------------------------------------------------------------------------------------

async def after_run(services: AppServices, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> dict[str, Any] | None:
    """Update generation fitness after a run ends; in FULLY_AUTONOMOUS mode roll back regressions and evolve again."""
    scope = Scope(tenant_id, workspace_id)
    async with scoped_session(services.engine, tenant_id, workspace_id) as session:
        run = await session.get(WorkflowRun, run_id)
        if run is None or run.status not in FINISHED:
            return None
        row = await session.scalar(select(WorkflowTopologyVersion).where(WorkflowTopologyVersion.workflow_id == run.workflow_id))
        if row is None:
            return None
        policy, versions = await ensure_lineage(session, scope, run.workflow_id)
        await refresh_metrics(session, versions)
        if policy.auto_evolve_policy != "FULLY_AUTONOMOUS" or row.workflow_id != policy.active_workflow_id:
            return {"status": "measured", "version": row.version_number, "fitness": row.fitness}
        root = next((item for item in versions if item.parent_version is None), versions[0])
        parent = next((item for item in versions if item.version_number == row.parent_version), None)
        if parent is not None:
            decision = FitnessTracker().evaluate(stats_from_row(row), stats_from_row(parent), stats_from_row(root))
            if decision.rollback:
                await rollback_to(session, scope, policy, versions, parent, decision.reason)
                return {"status": "rolled_back", "to_version": parent.version_number, "reason": decision.reason,
                        "child_fitness": decision.child_fitness, "parent_fitness": decision.parent_fitness}
        workflow_id = row.workflow_id
    try:
        outcome = await evolve(services, scope, workflow_id, origin="autonomous", auto=True)
    except HTTPException as error:
        logger.info("Autonomous evolution skipped: %s", error.detail)
        return {"status": "measured", "note": str(error.detail)}
    return {"status": outcome.get("status"), "version": outcome.get("version")}
