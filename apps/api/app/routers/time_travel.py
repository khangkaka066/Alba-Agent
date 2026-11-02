"""Tenant-scoped checkpoint inspection, rewind and A/B child runs."""

from __future__ import annotations

import difflib
import json
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.auth.context import TenantContext, require_role
from app.models import AuditLog, RunCheckpoint, TokenUsageLog, Workflow, WorkflowRun
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from flows.state import WorkflowState
from time_travel.replay import fork_state, rewind_state

router = APIRouter(tags=["time-travel"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "run"))]


class RewindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mutated_state: dict[str, Any] | None = None
    node_overrides: dict[str, Any] = Field(default_factory=dict)


class ForkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_a: dict[str, Any] = Field(default_factory=dict)
    branch_b: dict[str, Any] = Field(default_factory=dict)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_a_run_id: UUID
    branch_b_run_id: UUID


async def _historical_state(request: Request, context: TenantContext, run_id: UUID, checkpoint_id: UUID) -> tuple[WorkflowRun, WorkflowState]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        run = await session.get(WorkflowRun, run_id)
        checkpoint = await session.get(RunCheckpoint, checkpoint_id)
        if run is None or checkpoint is None or checkpoint.run_id != run_id:
            raise not_found("Run checkpoint is not visible in this workspace")
        return run, WorkflowState.model_validate(checkpoint.state)


async def _queue_branch(request: Request, context: TenantContext, source_run: WorkflowRun,
                        state: WorkflowState, overrides: dict[str, Any], name: str) -> UUID:
    services = get_services(request)
    run_id = state.run_id
    input_data = dict(state.input_data)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        workflow = await session.get(Workflow, source_run.workflow_id)
        if workflow is None:
            raise not_found("Workflow for this checkpoint is unavailable")
        nodes = cast(list[dict[str, Any]], workflow.spec.get("nodes", []))
        target_node = next((node.get("id") for node in nodes if isinstance(node, dict) and node.get("id") not in state.completed_nodes and node.get("kind") != "start"), None)
        if overrides and target_node is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "No pending node accepts replay overrides")
        if overrides and target_node is not None:
            input_data["_nexus_node_overrides"] = {target_node: overrides}
        session.add(WorkflowRun(id=run_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                workflow_id=source_run.workflow_id, input_data=input_data, status="queued"))
        state.status = "running"
        session.add(RunCheckpoint(id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                  run_id=run_id, sequence=1, state=state.model_dump(mode="json")))
        session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id,
                             action="workflow_run.replayed", target_type="workflow_run", target_id=run_id,
                             details={"source_run_id": str(source_run.id), "branch": name, "completed_nodes": state.completed_nodes}))
    await services.dispatcher.workflow(context.tenant_id, context.workspace_id, run_id)
    return run_id


@router.get("/api/v1/runs/{run_id}/checkpoints")
async def list_checkpoints(run_id: UUID, request: Request, context: READ) -> list[dict[str, object]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(RunCheckpoint).where(RunCheckpoint.run_id == run_id).order_by(RunCheckpoint.sequence))).all()
        return [{"id": str(row.id), "sequence": row.sequence, "state": row.state,
                 "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/api/v1/runs/{run_id}/checkpoints/{checkpoint_id}/rewind", status_code=status.HTTP_202_ACCEPTED)
async def rewind(run_id: UUID, checkpoint_id: UUID, body: RewindRequest, request: Request, context: BUILD) -> dict[str, object]:
    source, historical = await _historical_state(request, context, run_id, checkpoint_id)
    if historical.status == "failed" and not historical.completed_nodes:
        raise HTTPException(status.HTTP_409_CONFLICT, "Checkpoint contains no completed node to replay from")
    branch = rewind_state(historical, mutated_state=body.mutated_state, node_overrides=body.node_overrides)
    child_id = await _queue_branch(request, context, source, branch.state, branch.node_overrides, "Replay")
    return {"run_id": str(child_id), "source_run_id": str(run_id), "checkpoint_id": str(checkpoint_id), "status": "queued"}


@router.post("/api/v1/runs/{run_id}/checkpoints/{checkpoint_id}/fork", status_code=status.HTTP_202_ACCEPTED)
async def fork(run_id: UUID, checkpoint_id: UUID, body: ForkRequest, request: Request, context: BUILD) -> dict[str, object]:
    source, historical = await _historical_state(request, context, run_id, checkpoint_id)
    branches = fork_state(historical, body.branch_a, body.branch_b)
    a_id = await _queue_branch(request, context, source, branches[0].state, branches[0].node_overrides, "Branch A")
    b_id = await _queue_branch(request, context, source, branches[1].state, branches[1].node_overrides, "Branch B")
    return {"source_run_id": str(run_id), "checkpoint_id": str(checkpoint_id),
            "branch_a": {"run_id": str(a_id), "status": "queued"},
            "branch_b": {"run_id": str(b_id), "status": "queued"},
            "comparison": {"output_diff": None, "latency_delta_ms": None, "cost_delta_usd": None, "validation_status": "pending"}}


@router.post("/api/v1/runs/compare")
async def compare_runs(body: CompareRequest, request: Request, context: READ) -> dict[str, object]:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        runs = [await session.get(WorkflowRun, body.branch_a_run_id), await session.get(WorkflowRun, body.branch_b_run_id)]
        if runs[0] is None or runs[1] is None:
            raise not_found("One or both runs are not visible in this workspace")
        checkpoints = []
        totals = []
        for run in (runs[0], runs[1]):
            assert run is not None
            checkpoint = await session.scalar(select(RunCheckpoint).where(RunCheckpoint.run_id == run.id).order_by(RunCheckpoint.sequence.desc()).limit(1))
            checkpoints.append(WorkflowState.model_validate(checkpoint.state) if checkpoint else None)
            usage = (await session.execute(select(
                func.coalesce(func.sum(TokenUsageLog.total_cost_usd), 0),
                func.coalesce(func.sum(TokenUsageLog.latency_ms), 0),
            ).where(TokenUsageLog.run_id == run.id))).one()
            totals.append((float(usage[0]), int(usage[1])))
    if checkpoints[0] is None or checkpoints[1] is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Both branch runs need checkpoints before comparison")
    output_a = json.dumps(checkpoints[0].node_outputs, indent=2, sort_keys=True)
    output_b = json.dumps(checkpoints[1].node_outputs, indent=2, sort_keys=True)
    return {"branch_a_run_id": str(body.branch_a_run_id), "branch_b_run_id": str(body.branch_b_run_id),
            "branch_a_status": checkpoints[0].status, "branch_b_status": checkpoints[1].status,
            "output_diff": "".join(difflib.unified_diff(output_a.splitlines(keepends=True), output_b.splitlines(keepends=True), fromfile="Branch A", tofile="Branch B")),
            "latency_delta_ms": totals[1][1] - totals[0][1], "cost_delta_usd": totals[1][0] - totals[0][0],
            "validation_status": "complete" if checkpoints[0].status == checkpoints[1].status == "completed" else "incomplete"}
