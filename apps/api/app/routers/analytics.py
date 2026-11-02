"""Tenant-scoped model and sandbox usage aggregates."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.auth.context import TenantContext, require_role
from app.models import AuditLog, DistillationRecommendation, GoldenTraceRecord, TokenUsageLog, Workflow
from app.models.scope import scoped_session
from app.routers.common import get_services
from nexus_core_schema.models import WorkflowSpec

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


class DistillationHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    live_error_rate: float = Field(ge=0, le=1)
    baseline_error_rate: float = Field(ge=0, le=1)


@router.get("/usage")
async def usage_analytics(
    request: Request,
    context: READ,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    workflow_id: UUID | None = None,
    run_id: UUID | None = None,
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        filters = [TokenUsageLog.created_at >= cutoff]
        if workflow_id is not None:
            filters.append(TokenUsageLog.workflow_id == workflow_id)
        if run_id is not None:
            filters.append(TokenUsageLog.run_id == run_id)
        totals = (await session.execute(select(
            func.coalesce(func.sum(TokenUsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(TokenUsageLog.completion_tokens), 0),
            func.coalesce(func.sum(TokenUsageLog.total_cost_usd), Decimal("0")),
            func.coalesce(func.sum(TokenUsageLog.sandbox_compute_seconds), Decimal("0")),
            func.coalesce(func.avg(TokenUsageLog.latency_ms), 0),
        ).where(*filters))).one()
        grouped = (await session.execute(select(
            TokenUsageLog.workflow_id,
            func.sum(TokenUsageLog.total_cost_usd),
            func.sum(TokenUsageLog.prompt_tokens),
            func.sum(TokenUsageLog.completion_tokens),
            func.sum(TokenUsageLog.sandbox_compute_seconds),
            func.avg(TokenUsageLog.latency_ms),
        ).where(*filters).group_by(TokenUsageLog.workflow_id).order_by(TokenUsageLog.workflow_id))).all()
    return {
        "tenant_id": str(context.tenant_id), "workspace_id": str(context.workspace_id),
        "window_days": days,
        "totals": {
            "prompt_tokens": int(totals[0]), "completion_tokens": int(totals[1]),
            "total_cost_usd": str(totals[2]), "sandbox_compute_seconds": str(totals[3]),
            "average_latency_ms": float(totals[4]),
        },
        "by_workflow": [
            {"workflow_id": str(row[0]) if row[0] else None, "total_cost_usd": str(row[1]),
             "prompt_tokens": int(row[2]), "completion_tokens": int(row[3]),
             "sandbox_compute_seconds": str(row[4]), "average_latency_ms": float(row[5])}
            for row in grouped
        ],
    }


@router.get("/distillation/recommendations")
async def distillation_recommendations(request: Request, context: READ) -> list[dict[str, object]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(DistillationRecommendation).order_by(DistillationRecommendation.created_at.desc()))).all()
        return [{"id": str(row.id), "agent_id": row.agent_id, "task_signature": row.task_signature,
                 "candidate_model": row.candidate_model, "metrics": row.metrics,
                 "few_shot_examples": row.few_shot_examples, "status": row.status} for row in rows]


@router.post("/distillation/recommendations/{recommendation_id}/apply")
async def apply_distillation_recommendation(recommendation_id: UUID, request: Request, context: BUILD) -> dict[str, object]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(DistillationRecommendation).where(DistillationRecommendation.id == recommendation_id).with_for_update())
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation is not visible in this workspace")
        if row.status != "recommended":
            raise HTTPException(status.HTTP_409_CONFLICT, "Recommendation is no longer available")
        workflows = (await session.scalars(select(Workflow).order_by(Workflow.version.desc()))).all()
        source = next((workflow for workflow in workflows if any(
            node.kind == "crew" and any(agent.id == row.agent_id for agent in node.agents)
            for node in WorkflowSpec.model_validate(workflow.spec).nodes
        )), None)
        if source is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "No workspace workflow contains this agent")
        spec = WorkflowSpec.model_validate(source.spec)
        nodes: list[Any] = []
        updated = False
        rollback_data: dict[str, object] = {"source_workflow_id": str(source.id), "agents": {}, "tasks": {}}
        examples_block = "\n\nVerified examples for this task:\n" + json.dumps(row.few_shot_examples, ensure_ascii=False, sort_keys=True)
        for node in spec.nodes:
            if node.kind != "crew":
                nodes.append(node)
                continue
            agents = tuple(agent.model_copy(update={"model": row.candidate_model}) if agent.id == row.agent_id else agent for agent in node.agents)
            tasks = tuple(task.model_copy(update={"description": task.description + examples_block}) if task.agent_id == row.agent_id else task for task in node.tasks)
            if any(agent.id == row.agent_id for agent in node.agents):
                original_agent = next(agent for agent in node.agents if agent.id == row.agent_id)
                rollback_data["agents"] = {row.agent_id: original_agent.model}
                rollback_data["tasks"] = {task.id: task.description for task in node.tasks if task.agent_id == row.agent_id}
                updated = True
                node = node.model_copy(update={"agents": agents, "tasks": tasks})
            nodes.append(node)
        if not updated:
            raise HTTPException(status.HTTP_409_CONFLICT, "Recommendation target is no longer available")
        latest_version = await session.scalar(select(func.max(Workflow.version)).where(Workflow.name == source.name))
        version = int(latest_version or source.version) + 1
        switched = spec.model_copy(update={"id": uuid4(), "version": version, "nodes": tuple(nodes)})
        row.metrics = {**row.metrics, "rollback": rollback_data}
        session.add(Workflow(id=switched.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                             name=source.name, version=version, spec=switched.model_dump(mode="json")))
        row.status = "applied"
        session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                             actor_id=context.user_id, action="finops.distillation_applied",
                             target_type="distillation_recommendation", target_id=row.id,
                             details={"model": row.candidate_model, "agent_id": row.agent_id}))
        return {"id": str(row.id), "status": row.status, "candidate_model": row.candidate_model,
                "few_shot_examples": row.few_shot_examples, "workflow_id": str(switched.id), "workflow_version": version}


@router.post("/distillation/recommendations/{recommendation_id}/health")
async def check_distillation_health(recommendation_id: UUID, body: DistillationHealth, request: Request, context: BUILD) -> dict[str, object]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(DistillationRecommendation).where(DistillationRecommendation.id == recommendation_id).with_for_update())
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation is not visible in this workspace")
        rolled_back = row.status == "applied" and body.live_error_rate > body.baseline_error_rate * 1.2
        rollback_version: int | None = None
        if rolled_back:
            rollback = row.metrics.get("rollback")
            if isinstance(rollback, dict):
                workflows = (await session.scalars(select(Workflow).order_by(Workflow.version.desc()))).all()
                source = next((workflow for workflow in workflows if any(
                    node.kind == "crew" and any(agent.id == row.agent_id for agent in node.agents)
                    for node in WorkflowSpec.model_validate(workflow.spec).nodes
                )), None)
                if source is not None:
                    spec = WorkflowSpec.model_validate(source.spec)
                    prior_agents = rollback.get("agents", {})
                    prior_tasks = rollback.get("tasks", {})
                    nodes: list[Any] = []
                    for node in spec.nodes:
                        if node.kind != "crew":
                            nodes.append(node)
                            continue
                        agents = tuple(agent.model_copy(update={"model": prior_agents[row.agent_id]}) if agent.id == row.agent_id and isinstance(prior_agents, dict) and isinstance(prior_agents.get(row.agent_id), str) else agent for agent in node.agents)
                        tasks = tuple(task.model_copy(update={"description": prior_tasks[task.id]}) if isinstance(prior_tasks, dict) and isinstance(prior_tasks.get(task.id), str) else task for task in node.tasks)
                        nodes.append(node.model_copy(update={"agents": agents, "tasks": tasks}))
                    latest_version = await session.scalar(select(func.max(Workflow.version)).where(Workflow.name == source.name))
                    rollback_version = int(latest_version or source.version) + 1
                    restored = spec.model_copy(update={"id": uuid4(), "version": rollback_version, "nodes": tuple(nodes)})
                    session.add(Workflow(id=restored.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                         name=source.name, version=rollback_version, spec=restored.model_dump(mode="json")))
            row.status = "rolled_back"
            session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                 actor_id=None, action="finops.distillation_rollback",
                                 target_type="distillation_recommendation", target_id=row.id,
                                 details={"live_error_rate": body.live_error_rate, "baseline_error_rate": body.baseline_error_rate}))
        return {"id": str(row.id), "status": row.status, "rolled_back": rolled_back,
                "rollback_workflow_version": rollback_version if rolled_back else None}


@router.get("/distillation/traces/count")
async def golden_trace_count(agent_id: str, task_signature: str, request: Request, context: READ) -> dict[str, int]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        count = await session.scalar(select(func.count(GoldenTraceRecord.id)).where(
            GoldenTraceRecord.agent_id == agent_id, GoldenTraceRecord.task_signature == task_signature))
    return {"count": int(count or 0), "minimum_for_evaluation": 20}
