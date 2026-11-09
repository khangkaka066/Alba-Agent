"""Durable scoped checkpoints with a Redis latest-state cache."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import ApprovalRequest, AuditLog, RunCheckpoint, Workflow, WorkflowRun, WorkspaceMember
from app.models.scope import scoped_session
from flows.state import WorkflowState

Decision = Literal["allowed_once", "always_allowed", "denied"]
ROLE_RANK = {"viewer": 0, "builder": 1, "admin": 2, "owner": 3}


class RunCancelled(asyncio.CancelledError):
    """A user-requested stop, carrying the last safe state when available."""

    def __init__(self, state: WorkflowState | None = None) -> None:
        super().__init__("The user stopped this run")
        self.state = state


class CheckpointStore:
    def __init__(self, engine: AsyncEngine, redis: Redis, cache_seconds: int = 86_400) -> None:
        self._engine = engine
        self._redis = redis
        self._cache_seconds = cache_seconds

    @staticmethod
    def cache_key(tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> str:
        return f"run:{tenant_id}:{workspace_id}:{run_id}:checkpoint"

    @staticmethod
    def cancellation_key(tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> str:
        return f"run:{tenant_id}:{workspace_id}:{run_id}:cancel-requested"

    async def assert_running(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, state: WorkflowState | None = None) -> None:
        if await self._redis.get(self.cancellation_key(tenant_id, workspace_id, run_id)):
            raise RunCancelled(state)

    async def create_run(self, state: WorkflowState) -> None:
        async with scoped_session(self._engine, state.tenant_id, state.workspace_id) as session:
            workflow = await session.scalar(select(Workflow).where(Workflow.id == state.workflow_id))
            if workflow is None:
                raise LookupError("Workflow is not visible in this workspace")
            existing = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == state.run_id))
            if existing is not None:
                raise ValueError("Workflow run already exists")
            session.add(WorkflowRun(
                id=state.run_id,
                tenant_id=state.tenant_id,
                workspace_id=state.workspace_id,
                workflow_id=state.workflow_id,
                status="queued",
            ))

    async def save(self, state: WorkflowState) -> WorkflowState:
        if state.status != "cancelled":
            await self.assert_running(state.tenant_id, state.workspace_id, state.run_id, state)
        async with scoped_session(self._engine, state.tenant_id, state.workspace_id) as session:
            run = await session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.id == state.run_id)
                .with_for_update()
            )
            if run is None:
                raise LookupError("Workflow run is not visible in this workspace")
            await self._append_checkpoint(session, run, state)
        await self._redis.set(
            self.cache_key(state.tenant_id, state.workspace_id, state.run_id),
            state.model_dump_json(),
            ex=self._cache_seconds,
        )
        return state

    async def record_failure(self, state: WorkflowState, failure: dict[str, Any]) -> None:
        """Keep the structured reason on the run so it can be shown, and retried, after the worker is gone."""
        async with scoped_session(self._engine, state.tenant_id, state.workspace_id) as session:
            run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == state.run_id).with_for_update())
            if run is not None:
                run.failure = failure

    @staticmethod
    async def _append_checkpoint(session: AsyncSession, run: WorkflowRun, state: WorkflowState) -> None:
        if run.status == "cancelled" and state.status != "cancelled":
            raise RunCancelled(state)
        latest = await session.scalar(
            select(func.max(RunCheckpoint.sequence)).where(RunCheckpoint.run_id == state.run_id)
        )
        state.sequence = (latest or 0) + 1
        run.status = state.status
        if state.status == "running" and run.started_at is None:
            run.started_at = datetime.now(timezone.utc)
        if state.status == "running" and run.failure is not None:
            run.failure, run.finished_at = None, None  # a retried run starts clean
        if state.status in ("completed", "failed", "cancelled"):
            run.finished_at = datetime.now(timezone.utc)
        session.add(RunCheckpoint(
            tenant_id=state.tenant_id,
            workspace_id=state.workspace_id,
            run_id=state.run_id,
            sequence=state.sequence,
            state=state.model_dump(mode="json"),
        ))

    async def load(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> WorkflowState:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            checkpoint = await session.scalar(
                select(RunCheckpoint)
                .where(RunCheckpoint.run_id == run_id)
                .order_by(RunCheckpoint.sequence.desc())
                .limit(1)
            )
            if checkpoint is None:
                raise LookupError("No checkpoint is visible for this run")
            db_state = WorkflowState.model_validate(checkpoint.state)
        cached = await self._redis.get(self.cache_key(tenant_id, workspace_id, run_id))
        if cached is not None:
            cache_state = WorkflowState.model_validate_json(cached)
            if cache_state == db_state:
                return cache_state
        return db_state

    async def request_approval(
        self,
        state: WorkflowState,
        node_id: str,
        action: str,
        required_role: str,
        timeout_seconds: int,
    ) -> UUID:
        await self.assert_running(state.tenant_id, state.workspace_id, state.run_id, state)
        if state.pending_approval_id is not None:
            raise ValueError("Workflow already has a pending approval")
        approval_id = uuid4()
        state.pending_approval_id = approval_id
        state.status = "paused"
        row = ApprovalRequest(
            id=approval_id,
            tenant_id=state.tenant_id,
            workspace_id=state.workspace_id,
            run_id=state.run_id,
            node_id=node_id,
            action=action,
            rationale=f"Workflow node {node_id} requires human approval",
            required_role=required_role,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds),
        )
        async with scoped_session(self._engine, state.tenant_id, state.workspace_id) as session:
            run = await session.scalar(
                select(WorkflowRun).where(WorkflowRun.id == state.run_id).with_for_update()
            )
            if run is None:
                raise LookupError("Workflow run is not visible in this workspace")
            if run.status != "running":
                raise ValueError("Workflow is not running without a pending approval")
            session.add(row)
            await self._append_checkpoint(session, run, state)
            session.add(AuditLog(
                tenant_id=state.tenant_id,
                workspace_id=state.workspace_id,
                actor_id=None,
                action="approval.requested",
                target_type="approval",
                target_id=row.id,
                details={"run_id": str(state.run_id), "node_id": node_id},
            ))
        await self._redis.set(
            self.cache_key(state.tenant_id, state.workspace_id, state.run_id),
            state.model_dump_json(), ex=self._cache_seconds,
        )
        return approval_id

    async def approval_status(
        self, tenant_id: UUID, workspace_id: UUID, approval_id: UUID
    ) -> str:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            row = await session.scalar(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
            if row is None:
                raise LookupError("Approval request is not visible in this workspace")
            return row.status

    async def resolve_approval(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        approval_id: UUID,
        user_id: UUID,
        decision: Decision,
    ) -> None:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            row = await session.scalar(
                select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update()
            )
            member = await session.scalar(
                select(WorkspaceMember).where(WorkspaceMember.user_id == user_id)
            )
            if row is None or member is None:
                raise LookupError("Approval or member is not visible in this workspace")
            if row.run_id:
                run = await session.get(WorkflowRun, row.run_id)
                if run is None or run.status == "cancelled" or await self._redis.get(self.cancellation_key(tenant_id, workspace_id, row.run_id)):
                    raise ValueError("The run has been stopped")
            if ROLE_RANK[member.role] < ROLE_RANK[row.required_role]:
                raise PermissionError("Member role cannot decide this approval")
            if row.status != "pending":
                raise ValueError("Approval has already been decided")
            now = datetime.now(timezone.utc)
            if row.expires_at is not None and row.expires_at < now:
                raise ValueError("Approval has expired")
            row.status = decision
            row.decided_by_user_id = user_id
            row.decided_at = now
            session.add(AuditLog(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_id=user_id,
                action="approval.resolved",
                target_type="approval",
                target_id=approval_id,
                details={"decision": decision},
            ))
