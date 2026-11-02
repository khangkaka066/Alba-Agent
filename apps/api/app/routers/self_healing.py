"""Review and apply tenant-scoped prompt patch proposals."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.auth.context import TenantContext, require_role
from app.models import AuditLog, PromptPatchProposal, Workflow
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from nexus_core_schema.models import WorkflowSpec

router = APIRouter(prefix="/api/v1/self-healing", tags=["self-healing"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


@router.get("/proposals")
async def list_proposals(request: Request, context: READ) -> list[dict[str, object]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(PromptPatchProposal).where(
            PromptPatchProposal.status == "pending").order_by(PromptPatchProposal.created_at.desc()))).all()
        return [{"id": str(row.id), "workflow_id": str(row.workflow_id), "agent_id": row.agent_id,
                 "target_field": row.target_field, "unified_diff": row.unified_diff,
                 "reviewer_comment": row.reviewer_comment, "status": row.status} for row in rows]


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: UUID, request: Request, context: BUILD) -> dict[str, object]:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        proposal = await session.scalar(select(PromptPatchProposal).where(
            PromptPatchProposal.id == proposal_id).with_for_update())
        if proposal is None:
            raise not_found("Prompt patch proposal is not visible in this workspace")
        if proposal.status != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, "Prompt patch proposal is no longer pending")
        source = await session.scalar(select(Workflow).where(Workflow.id == proposal.workflow_id))
        if source is None:
            raise not_found("Source workflow is unavailable")
        spec = WorkflowSpec.model_validate(source.spec)
        changed = False
        nodes = []
        for node in spec.nodes:
            if node.kind == "crew":
                agents = []
                for agent in node.agents:
                    if agent.id == proposal.agent_id:
                        field_name = proposal.target_field
                        if field_name in {"goal", "backstory"}:
                            agent = agent.model_copy(update={field_name: proposal.replacement_value})
                            changed = True
                        elif field_name == "guardrails":
                            agent = agent.model_copy(update={"guardrails": (*agent.guardrails, proposal.replacement_value)})
                            changed = True
                    agents.append(agent)
                tasks = []
                for task in node.tasks:
                    if task.agent_id == proposal.agent_id and proposal.target_field == "task_description":
                        task = task.model_copy(update={"description": proposal.replacement_value})
                        changed = True
                    tasks.append(task)
                if changed:
                    node = node.model_copy(update={"agents": tuple(agents), "tasks": tuple(tasks)})
            nodes.append(node)
        if not changed:
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposal target no longer matches a workflow agent or task")
        latest_version = await session.scalar(select(func.max(Workflow.version)).where(Workflow.name == source.name))
        new_version = int(latest_version or source.version) + 1
        new_spec = spec.model_copy(update={"id": uuid4(), "version": new_version, "nodes": tuple(nodes)})
        session.add(Workflow(id=new_spec.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                             name=source.name, version=new_version, spec=new_spec.model_dump(mode="json")))
        proposal.status = "applied"
        proposal.applied_workflow_version = new_version
        session.add(AuditLog(tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                             actor_id=context.user_id, action="self_healing.proposal_applied",
                             target_type="workflow", target_id=new_spec.id,
                             details={"proposal_id": str(proposal_id), "version": new_version}))
        return {"proposal_id": str(proposal_id), "workflow_id": str(new_spec.id), "version": new_version,
                "workflow": new_spec.model_dump(mode="json")}
