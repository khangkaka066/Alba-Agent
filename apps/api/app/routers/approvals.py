"""Resolve a scoped approval and resume its persisted checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
import os
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.auth.context import TenantContext, require_role
from app.models import ApprovalRequest, AuditLog, GoldenTraceRecord, PromptPatchProposal, RunCheckpoint, TokenUsageLog, Workflow, WorkflowRun
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])
APPROVE = Annotated[TenantContext, Depends(require_role("builder", "approve"))]


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["allow_once", "always_allow_routine", "deny"]
    feedback: str | None = Field(default=None, max_length=8000)
    original_ai_output: str | None = Field(default=None, max_length=24000)
    human_corrected_output: str | None = Field(default=None, max_length=24000)
    agent_id: str | None = Field(default=None, max_length=100)
    target_field: Literal["goal", "backstory", "task_description", "guardrails"] = "task_description"


@router.post("/{approval_id}/resolve")
async def resolve_approval(approval_id: UUID, body: ApprovalDecision, request: Request, background_tasks: BackgroundTasks, context: APPROVE) -> dict[str, object]:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        approval = await session.get(ApprovalRequest, approval_id)
        if approval is None:
            raise not_found("Approval is not visible in this workspace")
        if approval.status != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, "Approval has already been resolved")
        if context.role not in {"owner", "admin", "builder"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Workspace role cannot resolve approvals")
        if approval.required_role == "admin" and context.role not in {"owner", "admin"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Approval requires an administrator")
        if approval.required_role == "owner" and context.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Approval requires an owner")
        run_id = approval.run_id or approval.routine_run_id
        if run_id is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Approval has no associated run")
    try:
        result = await services.approvals(context.tenant_id, context.workspace_id, context.user_id).resume_from_approval(run_id, body.decision)
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except (LookupError, ValueError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if body.feedback and body.feedback.strip():
        from learning_transfer.distiller import DistillationCandidate, DistillationTrigger, EpisodicKnowledgeDistiller
        from nexus_core_schema.models import PropagationScope

        async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
            approval = await session.get(ApprovalRequest, approval_id)
            node_id = approval.node_id if approval is not None else "approval-review"
        capsule = EpisodicKnowledgeDistiller().distill(DistillationCandidate(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            source_agent_id=f"human_reviewer_{node_id}", source_role="Human reviewer",
            trigger=DistillationTrigger.APPROVAL_CORRECTION,
            heuristic="", preconditions="A similar approval boundary or output correction is encountered",
            domain_tags=("approval-correction",), reviewer_feedback=body.feedback,
            propagation_scope=PropagationScope.WORKSPACE_QUARANTINE,
        ))
        if capsule is not None:
            from app.learning import save_capsule

            await save_capsule(services, capsule)
    if body.original_ai_output and body.human_corrected_output and body.feedback:
        from learning_transfer.self_healing import SelfHealingOptimizer

        analysis = SelfHealingOptimizer().analyze(
            body.original_ai_output, body.human_corrected_output, body.feedback,
            target_field=body.target_field, agent_id=body.agent_id or f"reviewed_{approval_id.hex[:12]}",
        )
        async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
            approval = await session.get(ApprovalRequest, approval_id)
            source_run = await session.get(WorkflowRun, approval.run_id) if approval and approval.run_id else None
            workflow = await session.get(Workflow, source_run.workflow_id) if source_run else None
            proposal_agent_id = body.agent_id or (f"reviewed_{approval.node_id}" if approval else f"reviewed_{approval_id.hex[:12]}")
            if workflow is not None:
                session.add(PromptPatchProposal(
                    tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                    workflow_id=workflow.id, source_approval_id=approval_id,
                    agent_id=proposal_agent_id,
                    target_field=body.target_field,
                    original_output=body.original_ai_output,
                    corrected_output=body.human_corrected_output,
                    reviewer_comment=body.feedback,
                    unified_diff=analysis.proposal.unified_diff,
                    replacement_value=analysis.proposal.after,
                ))
                session.add(AuditLog(
                    tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                    actor_id=context.user_id, action="self_healing.proposal_created",
                    target_type="workflow", target_id=workflow.id,
                    details={"approval_id": str(approval_id), "agent_id": proposal_agent_id},
                ))
                capsule_fields = analysis.proposal.knowledge_capsule
            else:
                capsule_fields = None
        if capsule_fields:
            from learning_transfer.distiller import DistillationCandidate, DistillationTrigger, EpisodicKnowledgeDistiller
            from nexus_core_schema.models import PropagationScope
            capsule = EpisodicKnowledgeDistiller().distill(DistillationCandidate(
                tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                source_agent_id=str(capsule_fields["source_agent_id"]), source_role=str(capsule_fields["source_role"]),
                trigger=DistillationTrigger.APPROVAL_CORRECTION,
                heuristic=str(capsule_fields["distilled_heuristic"]),
                preconditions=str(capsule_fields["trigger_preconditions"]),
                domain_tags=tuple(capsule_fields["source_domain_tags"]), reviewer_feedback=body.feedback,
                propagation_scope=PropagationScope.WORKSPACE_QUARANTINE,
            ))
            if capsule is not None:
                from app.learning import save_capsule
                await save_capsule(services, capsule)
    if body.decision != "deny" and not body.human_corrected_output and not body.feedback and run_id is not None:
        frontier_models = {item.strip() for item in os.environ.get(
            "NEXUS_GOLDEN_TRACE_MODELS", "openai/gpt-4.1,anthropic/claude-sonnet-4,gemini/gemini-2.5-pro"
        ).split(",") if item.strip()}
        evaluation_targets: set[tuple[str, str]] = set()
        async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
            run = await session.get(WorkflowRun, run_id)
            workflow = await session.get(Workflow, run.workflow_id) if run else None
            checkpoint = await session.scalar(select(RunCheckpoint).where(
                RunCheckpoint.run_id == run_id).order_by(RunCheckpoint.sequence.desc()).limit(1))
            if workflow is not None and checkpoint is not None:
                state = checkpoint.state
                completed = set(cast(list[str], state.get("completed_nodes", [])))
                outputs = cast(dict[str, Any], state.get("node_outputs", {}))
                input_payload = cast(dict[str, Any], state.get("input_data", {}))
                spec = workflow.spec
                for node in cast(list[dict[str, Any]], spec.get("nodes", [])):
                    if not isinstance(node, dict) or node.get("kind") != "crew" or node.get("id") not in completed:
                        continue
                    agents = node.get("agents", [])
                    tasks = node.get("tasks", [])
                    if not agents or not tasks or not isinstance(outputs, dict) or node.get("id") not in outputs:
                        continue
                    agent = agents[0]
                    agent_id = str(agent.get("id", ""))
                    model = str(agent.get("model", ""))
                    if not agent_id or model not in frontier_models:
                        continue
                    signature_payload = json.dumps({"tasks": [task.get("description") for task in tasks], "schema": tasks[-1].get("output_schema")}, sort_keys=True)
                    signature = hashlib.sha256(signature_payload.encode()).hexdigest()
                    existing = await session.scalar(select(GoldenTraceRecord.id).where(
                        GoldenTraceRecord.run_id == run_id, GoldenTraceRecord.agent_id == agent_id,
                        GoldenTraceRecord.task_signature == signature))
                    if existing is not None:
                        continue
                    usage = (await session.execute(select(
                        func.coalesce(func.sum(TokenUsageLog.total_cost_usd), 0),
                        func.coalesce(func.avg(TokenUsageLog.latency_ms), 0),
                    ).where(TokenUsageLog.run_id == run_id, TokenUsageLog.agent_name == agent_id))).one()
                    raw_input = json.dumps(input_payload, ensure_ascii=False)
                    safe_input = re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+", "[REDACTED]", raw_input)
                    safe_input = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[REDACTED_EMAIL]", safe_input, flags=re.IGNORECASE)
                    try:
                        safe_payload = json.loads(safe_input)
                    except json.JSONDecodeError:
                        safe_payload = {"redacted_input": True}
                    if isinstance(safe_payload, dict):
                        for sensitive_key in ("dataset", "dataset_base64", "sandbox_files", "file", "email", "phone", "customer_name"):
                            safe_payload.pop(sensitive_key, None)
                    clean_output = outputs[node["id"]]
                    retry_count = clean_output.get("retry_and_error_turns", 0) if isinstance(clean_output, dict) else 0
                    if retry_count:
                        continue
                    session.add(GoldenTraceRecord(
                        tenant_id=context.tenant_id, workspace_id=context.workspace_id, run_id=run_id,
                        agent_id=agent_id, task_signature=signature, input_payload=safe_payload,
                        verified_output=clean_output if isinstance(clean_output, dict) else {"output": clean_output},
                        model_used=model, cost_usd=usage[0], latency_ms=int(usage[1]),
                    ))
                    await session.flush()
                    trace_count = await session.scalar(select(func.count(GoldenTraceRecord.id)).where(
                        GoldenTraceRecord.agent_id == agent_id,
                        GoldenTraceRecord.task_signature == signature,
                    ))
                    if int(trace_count or 0) >= 20:
                        evaluation_targets.add((agent_id, signature))
        if evaluation_targets:
            from app.finops import shadow_distill
            for agent_id, signature in evaluation_targets:
                background_tasks.add_task(shadow_distill, services, context.tenant_id, context.workspace_id, agent_id, signature)
    if isinstance(result, str):
        return {"approval_id": str(approval_id), "decision": body.decision, "status": result}
    return {"approval_id": str(approval_id), "decision": body.decision, "status": result.status, "run_id": str(run_id), "outputs": result.node_outputs}
