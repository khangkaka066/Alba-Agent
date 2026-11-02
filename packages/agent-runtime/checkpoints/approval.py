"""Human decisions for workflow and routine checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal, cast
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import ApprovalRequest, AuditLog, BotRoutine, RoutineRun, WorkflowRun
from app.models.scope import scoped_session
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.store import CheckpointStore, Decision
from flows.compiler import CompiledWorkflow
from flows.compiler import PauseRequested
from flows.state import WorkflowState
from nexus_computer_sandbox.supervisor import ComputerAccess
from nexus_core_schema.models import RuntimeEventType

DecisionInput = Literal["allow_once", "always_allow_routine", "deny"]
WorkflowLoader = Callable[[UUID], Awaitable[CompiledWorkflow]]
RoutineResumer = Callable[[UUID], Awaitable[str]]


@dataclass(frozen=True)
class ActionIntent:
    kind: Literal["external_email", "external_action", "destructive_command", "high_spend", "other"]
    description: str
    amount_usd: Decimal = Decimal("0")


class BoundaryPolicy:
    def __init__(self, high_spend_usd: Decimal = Decimal("10")) -> None:
        if high_spend_usd <= 0:
            raise ValueError("High-spend threshold must be positive")
        self.high_spend_usd = high_spend_usd

    def requires_approval(self, intent: ActionIntent) -> bool:
        return intent.kind in ("external_email", "external_action", "destructive_command") or (
            intent.kind == "high_spend" and intent.amount_usd >= self.high_spend_usd
        )


class ApprovalCoordinator:
    def __init__(
        self,
        engine: AsyncEngine,
        redis: Redis,
        checkpoints: CheckpointStore,
        tenant_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        workflow_loader: WorkflowLoader,
        routine_resumer: RoutineResumer,
        policy: BoundaryPolicy | None = None,
        on_run_finished: Callable[[UUID], Awaitable[None]] | None = None,
    ) -> None:
        self._on_run_finished = on_run_finished
        self._engine = engine
        self._redis = redis
        self._checkpoints = checkpoints
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.actor_id = actor_id
        self._workflow_loader = workflow_loader
        self._routine_resumer = routine_resumer
        self._policy = policy or BoundaryPolicy()

    def _emitter(self, run_id: UUID) -> RuntimeEventEmitter:
        return RuntimeEventEmitter(self._redis, self.tenant_id, self.workspace_id, run_id)

    async def computer_guard(self, access: ComputerAccess, boundary: str, command: str) -> None:
        if (access.tenant_id, access.workspace_id) != (self.tenant_id, self.workspace_id) or access.run_id is None:
            raise PermissionError("Computer action lacks an approved run scope")
        if boundary not in ("external_email", "external_action", "destructive_command"):
            raise ValueError("Computer boundary category is not recognized")
        intent = ActionIntent(cast(Literal["external_email", "external_action", "destructive_command"], boundary), command)
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            grant = await session.scalar(select(ApprovalRequest).where(
                or_(ApprovalRequest.run_id == access.run_id, ApprovalRequest.routine_run_id == access.run_id),
                ApprovalRequest.node_id == f"boundary:{boundary}",
                ApprovalRequest.action == command,
                ApprovalRequest.status == "allowed_once",
                ApprovalRequest.grant_consumed_at.is_(None),
            ).order_by(ApprovalRequest.decided_at.desc()).with_for_update().limit(1))
            if grant is not None:
                grant.grant_consumed_at = datetime.now(timezone.utc)
                session.add(AuditLog(
                    tenant_id=self.tenant_id, workspace_id=self.workspace_id,
                    actor_id=self.actor_id, action="approval.grant_consumed",
                    target_type="approval", target_id=grant.id,
                    details={"run_id": str(access.run_id), "kind": boundary},
                ))
                return
            pending = await session.scalar(select(ApprovalRequest.id).where(
                or_(ApprovalRequest.run_id == access.run_id, ApprovalRequest.routine_run_id == access.run_id),
                ApprovalRequest.node_id == f"boundary:{boundary}",
                ApprovalRequest.action == command,
                ApprovalRequest.status == "pending",
            ).limit(1))
            if pending is not None:
                raise PauseRequested(f"Approval required: {pending}")
            workflow = await session.get(WorkflowRun, access.run_id)
            routine = await session.get(RoutineRun, access.run_id)
        if workflow is not None:
            if workflow.status != "running":
                raise PermissionError("Workflow cannot authorize a new computer action while paused")
            approval_id = await self.pause_workflow_for_action(access.run_id, intent)
        elif routine is not None:
            if routine.status != "running":
                raise PermissionError("Routine cannot authorize a new computer action while paused")
            approval_id = await self.pause_routine_for_action(access.run_id, intent)
        else:
            raise LookupError("No run is visible for this computer action")
        if approval_id is not None:
            raise PauseRequested(f"Approval required: {approval_id}")

    async def pause_workflow_for_action(self, run_id: UUID, intent: ActionIntent) -> UUID | None:
        if not self._policy.requires_approval(intent):
            return None
        state = await self._checkpoints.load(self.tenant_id, self.workspace_id, run_id)
        if state.status != "running" or state.pending_approval_id is not None:
            raise ValueError("Workflow is not running without a pending approval")
        state.pending_boundary = {"kind": intent.kind, "description": intent.description}
        approval_id = await self._checkpoints.request_approval(
            state, f"boundary:{intent.kind}", intent.description, "admin", 86_400,
        )
        await self._emitter(run_id).emit(
            RuntimeEventType.APPROVAL_REQUIRED,
            {"approval_id": str(approval_id), "action": intent.description, "kind": intent.kind, "required_role": "admin"},
        )
        return approval_id

    async def pause_routine_for_action(self, routine_run_id: UUID, intent: ActionIntent) -> UUID | None:
        if not self._policy.requires_approval(intent):
            return None
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            run = await session.scalar(select(RoutineRun).where(RoutineRun.id == routine_run_id).with_for_update())
            if run is None or run.status != "running":
                raise LookupError("Running routine is not visible in this workspace")
            routine = await session.scalar(select(BotRoutine).where(BotRoutine.id == run.routine_id))
            if routine is None:
                raise LookupError("Routine is not visible in this workspace")
            if f"boundary:{intent.kind}:{intent.description}" in routine.allowed_actions:
                return None
            row = ApprovalRequest(
                tenant_id=self.tenant_id, workspace_id=self.workspace_id,
                run_id=None, routine_run_id=routine_run_id,
                node_id=f"boundary:{intent.kind}", action=intent.description,
                rationale="Sensitive routine action requires human approval",
                required_role="admin", status="pending",
            )
            session.add(row)
            await session.flush()
            run.status = "paused"
            run.checkpoint = {**run.checkpoint, "pending_approval_id": str(row.id), "pending_action": intent.description, "stage": "paused"}
            session.add(AuditLog(
                tenant_id=self.tenant_id, workspace_id=self.workspace_id,
                actor_id=None, action="approval.requested", target_type="approval",
                target_id=row.id, details={"routine_run_id": str(routine_run_id), "kind": intent.kind},
            ))
            approval_id = row.id
        await self._emitter(routine_run_id).emit(
            RuntimeEventType.APPROVAL_REQUIRED,
            {"approval_id": str(approval_id), "action": intent.description, "kind": intent.kind, "required_role": "admin", "routine_run_id": str(routine_run_id)},
        )
        return approval_id

    async def resume_from_approval(self, run_id: UUID, decision: DecisionInput) -> WorkflowState | str:
        if decision not in ("allow_once", "always_allow_routine", "deny"):
            raise ValueError("Unknown approval decision")
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            approval = await session.scalar(
                select(ApprovalRequest).where(
                    or_(ApprovalRequest.run_id == run_id, ApprovalRequest.routine_run_id == run_id),
                ).order_by(
                    case((ApprovalRequest.status == "pending", 0), else_=1),
                    ApprovalRequest.created_at.desc(),
                ).limit(1)
            )
            if approval is None:
                raise LookupError("No approval is visible for this run")
            is_routine = approval.routine_run_id is not None
            if decision == "always_allow_routine" and not is_routine:
                raise ValueError("Routine-wide permission requires a routine run")
            approval_id = approval.id
            action = f"{approval.node_id}:{approval.action}"
            current_status = approval.status
        mapped: Decision
        if decision == "allow_once":
            mapped = "allowed_once"
        elif decision == "always_allow_routine":
            mapped = "always_allowed"
        else:
            mapped = "denied"
        if current_status == "pending":
            await self._checkpoints.resolve_approval(
                self.tenant_id, self.workspace_id, approval_id, self.actor_id, mapped,
            )
            await self._emitter(run_id).emit(
                RuntimeEventType.APPROVAL_RESOLVED,
                {"approval_id": str(approval_id), "decision": decision},
            )
        elif current_status != mapped:
            raise ValueError("Approval has already been decided differently")
        if is_routine:
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                run = await session.scalar(select(RoutineRun).where(RoutineRun.id == run_id).with_for_update())
                if run is None:
                    raise LookupError("Routine run disappeared after approval")
                if run.status == "completed":
                    return str(run.checkpoint.get("result", "completed"))
                if run.status == "failed" and decision == "deny":
                    return "denied"
                if decision == "always_allow_routine":
                    routine = await session.scalar(select(BotRoutine).where(BotRoutine.id == run.routine_id).with_for_update())
                    if routine is None:
                        raise LookupError("Routine disappeared after approval")
                    routine.allowed_actions = sorted(set(routine.allowed_actions) | {action})
                run.status = "failed" if decision == "deny" else "running"
                run.checkpoint = {**run.checkpoint, "decision": decision, "stage": "denied" if decision == "deny" else "approved"}
            if decision == "deny":
                await self._emitter(run_id).emit(RuntimeEventType.RUN_FAILED, {"error_type": "ApprovalDenied"})
                return "denied"
            return await self._routine_resumer(run_id)
        workflow = await self._workflow_loader(run_id)
        state = await self._checkpoints.load(self.tenant_id, self.workspace_id, run_id)
        result = state if state.status in ("completed", "failed") else await workflow.resume()
        if result.status in ("completed", "failed") and self._on_run_finished is not None and state.status not in ("completed", "failed"):
            await self._on_run_finished(run_id)
        if result.status in ("completed", "failed"):
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                routine = await session.scalar(select(RoutineRun).where(RoutineRun.workflow_run_id == run_id).with_for_update())
                if routine is not None and routine.status == "paused":
                    routine.status = result.status
                    routine.checkpoint = {**routine.checkpoint, "stage": result.status, "result": result.status}
        return result
