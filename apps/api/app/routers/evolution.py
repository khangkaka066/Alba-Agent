"""Team topology evolution: analyse runs, propose or apply a new generation, inspect lineage, roll back."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import evolution
from app.auth.context import TenantContext, require_role
from app.models import WorkflowEvolutionPolicy, WorkflowTopologyVersion
from app.models.scope import scoped_session
from app.routers.common import conflict, get_services, not_found

router = APIRouter(tags=["evolution"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


class EvolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_ids: list[UUID] | None = Field(default=None, max_length=10, description="Analyse these runs instead of the latest ones")
    operations: list[dict[str, Any]] | None = Field(default=None, max_length=12, description="Apply these mutation operators instead of planning from diagnostics")
    rationale: str = Field(default="", max_length=2000)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=2000)


class PolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_evolve_policy: Literal["SUGGEST_FIRST", "FULLY_AUTONOMOUS"]


def _scope(context: TenantContext) -> evolution.Scope:
    return evolution.Scope(context.tenant_id, context.workspace_id, context.user_id)


async def _version(versions: list[WorkflowTopologyVersion], number: int) -> WorkflowTopologyVersion:
    row = next((item for item in versions if item.version_number == number), None)
    if row is None:
        raise not_found(f"Generation v{number} does not exist in this lineage")
    return row


@router.post("/api/v1/workflows/{workflow_id}/evolve")
async def evolve_workflow(workflow_id: UUID, body: EvolveRequest, request: Request, context: BUILD) -> dict[str, Any]:
    return await evolution.evolve(
        get_services(request), _scope(context), workflow_id, origin="manual" if body.operations else "post_run",
        operations=body.operations, run_ids=body.run_ids, rationale=body.rationale,
    )


@router.get("/api/v1/workflows/{workflow_id}/generations")
async def list_generations(workflow_id: UUID, request: Request, context: READ, create: bool = True) -> dict[str, Any]:
    """Lineage of a workflow. ``create=false`` is a pure read for workflows that have never been evolved."""
    scope = _scope(context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        try:
            policy, versions = await evolution.ensure_lineage(session, scope, workflow_id, create=create)
        except LookupError:
            return {"lineage_id": None, "auto_evolve_policy": "SUGGEST_FIRST", "active_workflow_id": str(workflow_id), "active_version": None,
                    "generations": [], "trend": [], "lineage": ""}
        await evolution.refresh_metrics(session, versions)
        return evolution.lineage_view(policy, versions)


@router.get("/api/v1/workflows/{workflow_id}/generations/{version}")
async def get_generation(workflow_id: UUID, version: int, request: Request, context: READ) -> dict[str, Any]:
    scope = _scope(context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        policy, versions = await evolution.ensure_lineage(session, scope, workflow_id)
        row = await _version(versions, version)
        parent = next((item for item in versions if item.version_number == row.parent_version), None)
        return {**evolution.version_summary(row, policy), "spec": row.spec, "parent_spec": parent.spec if parent else None}


@router.post("/api/v1/workflows/{workflow_id}/generations/{version}/rollback")
async def rollback_generation(workflow_id: UUID, version: int, body: DecisionRequest, request: Request, context: BUILD) -> dict[str, Any]:
    scope = _scope(context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        policy, versions = await evolution.ensure_lineage(session, scope, workflow_id)
        target = await _version(versions, version)
        if target.workflow_id == policy.active_workflow_id:
            raise conflict(f"Generation v{version} is already the active team")
        await evolution.rollback_to(session, scope, policy, versions, target, body.note or f"Restored v{version} by user request")
        return evolution.lineage_view(policy, versions)


@router.post("/api/v1/workflows/{workflow_id}/generations/{version}/promote")
async def promote_generation(workflow_id: UUID, version: int, body: DecisionRequest, request: Request, context: BUILD) -> dict[str, Any]:
    scope = _scope(context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        policy, versions = await evolution.ensure_lineage(session, scope, workflow_id)
        row = await _version(versions, version)
        if row.status != "proposed":
            raise conflict(f"Generation v{version} is {row.status}, not a proposal")
        await evolution.promote(session, scope, policy, versions, row, body.note or "Approved by user")
        return evolution.lineage_view(policy, versions)


@router.post("/api/v1/workflows/{workflow_id}/generations/{version}/reject")
async def reject_generation(workflow_id: UUID, version: int, body: DecisionRequest, request: Request, context: BUILD) -> dict[str, Any]:
    scope = _scope(context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        policy, versions = await evolution.ensure_lineage(session, scope, workflow_id)
        row = await _version(versions, version)
        if row.status != "proposed":
            raise conflict(f"Generation v{version} is {row.status}, not a proposal")
        row.status, row.decision_note = "rejected", body.note or "Rejected by user"
        evolution._audit(session, scope, "workflow.topology_rejected", row, {"note": row.decision_note})
        return evolution.lineage_view(policy, versions)


@router.put("/api/v1/workflows/{workflow_id}/evolution-policy")
async def set_policy(workflow_id: UUID, body: PolicyRequest, request: Request, context: BUILD) -> dict[str, Any]:
    scope = _scope(context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        policy, versions = await evolution.ensure_lineage(session, scope, workflow_id)
        policy.auto_evolve_policy = body.auto_evolve_policy
        return evolution.lineage_view(policy, versions)


@router.get("/api/v1/evolution/lineages")
async def list_lineages(request: Request, context: READ) -> list[dict[str, Any]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        policies = (await session.scalars(select(WorkflowEvolutionPolicy).order_by(WorkflowEvolutionPolicy.created_at))).all()
        result: list[dict[str, Any]] = []
        for policy in policies:
            versions = list((await session.scalars(select(WorkflowTopologyVersion).where(WorkflowTopologyVersion.lineage_id == policy.lineage_id))).all())
            await evolution.refresh_metrics(session, versions)
            view = evolution.lineage_view(policy, versions)
            active = next((item for item in view["generations"] if item["is_active"]), None)
            result.append({
                "lineage_id": view["lineage_id"], "active_workflow_id": view["active_workflow_id"], "lineage": view["lineage"],
                "auto_evolve_policy": view["auto_evolve_policy"], "trend": view["trend"], "active": active,
                "pending_proposals": sum(1 for item in view["generations"] if item["status"] == "proposed"),
                "name": next((str(v.spec.get("name")) for v in versions if str(v.workflow_id) == view["active_workflow_id"]), None),
            })
        return result

