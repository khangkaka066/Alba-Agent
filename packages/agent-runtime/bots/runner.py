"""Scoped bot conversations and idempotent Markdown routine scheduling."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

import yaml  # type: ignore[import-untyped]
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import AuditLog, BotMessage, BotRoutine, PersistentBot, RoutineRun, Workflow, WorkflowRun
from app.models.scope import scoped_session
from nexusgen_bridge.sandbox_team import NexusGenSandboxRunner
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.approval import ActionIntent
from checkpoints.store import CheckpointStore
from crews.builder import CrewBuilder
from flows.compiler import CompiledWorkflow, FlowCompiler
from flows.state import WorkflowState
from nexus_core_schema.models import PersistentBotSpec, RuntimeEventType, WorkflowSpec
from nexus_model_gateway.router import BudgetExceeded


BotResponder = Callable[[PersistentBotSpec, tuple[tuple[str, str], ...]], Awaitable[str]]


BoundaryRequester = Callable[[UUID, ActionIntent], Awaitable[UUID | None]]

logger = logging.getLogger(__name__)



def _matches_field(field: str, value: int, minimum: int, maximum: int, *, sunday: bool = False) -> bool:
    for item in field.split(","):
        parts = item.split("/")
        if len(parts) > 2:
            raise ValueError("Invalid cron step")
        step = int(parts[1]) if len(parts) == 2 else 1
        if step < 1:
            raise ValueError("Cron step must be positive")
        base = parts[0]
        if base == "*":
            lower, upper = minimum, maximum
        elif "-" in base:
            left, right = base.split("-", 1)
            lower, upper = int(left), int(right)
        else:
            lower = upper = int(base)
        if sunday and base == "7":
            lower = upper = 0
        if lower < minimum or upper > maximum or lower > upper:
            raise ValueError("Cron value is outside its field range")
        if lower <= value <= upper and (value - lower) % step == 0:
            return True
    return False


def cron_matches(expression: str, when: datetime, timezone_name: str) -> bool:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron expression requires five fields")
    local = when.astimezone(ZoneInfo(timezone_name))
    minute, hour, day, month, weekday = fields
    day_match = _matches_field(day, local.day, 1, 31)
    weekday_match = _matches_field(weekday, (local.weekday() + 1) % 7, 0, 7, sunday=True)
    if day != "*" and weekday != "*":
        date_match = day_match or weekday_match
    else:
        date_match = day_match and weekday_match
    return (
        _matches_field(minute, local.minute, 0, 59) and
        _matches_field(hour, local.hour, 0, 23) and
        date_match and _matches_field(month, local.month, 1, 12)
    )


def _parse_markdown(source: str) -> tuple[dict[str, Any], str]:
    if not source.startswith("---\n"):
        return {}, source
    separator = source.find("\n---\n", 4)
    if separator < 0:
        raise ValueError("Markdown front matter is not closed")
    data = yaml.safe_load(source[4:separator])
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Markdown front matter must be an object")
    return data, source[separator + 5:].strip()


class BotRunner:
    def __init__(
        self,
        engine: AsyncEngine,
        redis: Redis,
        tenant_id: UUID,
        workspace_id: UUID,
        responder: BotResponder,
        sandbox_runner: NexusGenSandboxRunner,
        crew_builder: CrewBuilder | None = None,
        boundary_requester: BoundaryRequester | None = None,
    ) -> None:
        self._engine = engine
        self._redis = redis
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self._responder = responder
        self._sandbox_runner = sandbox_runner
        self._crew_builder = crew_builder
        self._boundary_requester = boundary_requester
        self._checkpoints = CheckpointStore(engine, redis)

    async def _bot(self, bot_id: UUID) -> PersistentBotSpec:
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            row = await session.get(PersistentBot, bot_id)
            if row is None:
                raise LookupError("Bot is not visible in this workspace")
            spec = PersistentBotSpec.model_validate(row.spec)
            if (spec.id, spec.tenant_id, spec.workspace_id) != (row.id, self.tenant_id, self.workspace_id):
                raise ValueError("Stored bot contract does not match its database scope")
            return spec

    async def history(self, bot_id: UUID, thread_id: UUID) -> tuple[tuple[str, str], ...]:
        await self._bot(bot_id)
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            rows = (await session.scalars(
                select(BotMessage).where(BotMessage.bot_id == bot_id, BotMessage.thread_id == thread_id)
                .order_by(BotMessage.created_at, BotMessage.id)
            )).all()
            return tuple((row.role, row.content) for row in rows)

    async def _append(self, bot_id: UUID, thread_id: UUID, role: str, content: str) -> None:
        if role not in ("user", "assistant", "system") or not content.strip():
            raise ValueError("Bot message role and content must be valid")
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            session.add(BotMessage(
                tenant_id=self.tenant_id, workspace_id=self.workspace_id,
                bot_id=bot_id, thread_id=thread_id, role=role, content=content,
            ))

    async def chat(self, bot_id: UUID, thread_id: UUID, content: str) -> str:
        bot = await self._bot(bot_id)
        await self._append(bot_id, thread_id, "user", content)
        try:
            response = await self._responder(bot, await self.history(bot_id, thread_id))
        except BudgetExceeded:
            notice = ("No model is available for this teammate. Add a provider key in Settings → Providers "
                      "or top up workspace credit, then send your message again.")
            await self._append(bot_id, thread_id, "system", notice)
            return notice
        except Exception:
            logger.exception("Teammate turn failed", extra={"bot_id": str(bot_id), "thread_id": str(thread_id)})
            notice = "The teammate could not answer this message. Check the model configuration and try again."
            await self._append(bot_id, thread_id, "system", notice)
            return notice
        await self._append(bot_id, thread_id, "assistant", response)
        return response

    async def load_workflow(self, run_id: UUID) -> CompiledWorkflow:
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            run = await session.get(WorkflowRun, run_id)
            if run is None:
                raise LookupError("Workflow run is not visible in this workspace")
            workflow = await session.get(Workflow, run.workflow_id)
            if workflow is None:
                raise LookupError("Workflow is not visible in this workspace")
            spec = WorkflowSpec.model_validate(workflow.spec)
        emitter = RuntimeEventEmitter(self._redis, self.tenant_id, self.workspace_id, run_id)
        return FlowCompiler(self._checkpoints, emitter, self._sandbox_runner, self._crew_builder).compile(spec, run_id)

    async def invoke_workflow(self, bot_id: UUID, workflow_id: UUID, task: str) -> WorkflowState:
        await self._bot(bot_id)
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            row = await session.get(Workflow, workflow_id)
            if row is None:
                raise LookupError("Workflow is not visible in this workspace")
            spec = WorkflowSpec.model_validate(row.spec)
        run_id = uuid4()
        emitter = RuntimeEventEmitter(self._redis, self.tenant_id, self.workspace_id, run_id)
        flow = FlowCompiler(self._checkpoints, emitter, self._sandbox_runner, self._crew_builder).compile(
            spec, run_id, {"task": task, "bot_id": str(bot_id)},
        )
        return await flow.run()

    async def _due(self, session: AsyncSession, routine: BotRoutine, when: datetime) -> datetime | None:
        if routine.interval_seconds is not None:
            scheduled = when.replace(microsecond=0)
            previous = await session.scalar(
                select(RoutineRun.scheduled_for).where(RoutineRun.routine_id == routine.id)
                .order_by(RoutineRun.scheduled_for.desc()).limit(1)
            )
            return scheduled if previous is None or (scheduled - previous).total_seconds() >= routine.interval_seconds else None
        scheduled = when.replace(second=0, microsecond=0)
        return scheduled if cron_matches(routine.cron_expression, when, routine.timezone) else None

    async def run_due(self, when: datetime | None = None) -> tuple[UUID, ...]:
        instant = when or datetime.now(timezone.utc)
        if instant.tzinfo is None:
            raise ValueError("Scheduler time must have a timezone")
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            routines = (await session.scalars(select(BotRoutine).where(BotRoutine.enabled.is_(True)))).all()
        started: list[UUID] = []
        for routine in routines:
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                locked = await session.scalar(select(BotRoutine).where(BotRoutine.id == routine.id).with_for_update())
                if locked is None or not locked.enabled:
                    continue
                scheduled = await self._due(session, locked, instant)
                if scheduled is None:
                    continue
                run_id = uuid4()
                statement = insert(RoutineRun).values(
                    id=run_id, tenant_id=self.tenant_id, workspace_id=self.workspace_id,
                    bot_id=locked.bot_id, routine_id=locked.id, scheduled_for=scheduled,
                    status="queued", checkpoint={"stage": "queued"},
                ).on_conflict_do_nothing(constraint="uq_routine_scheduled").returning(RoutineRun.id)
                inserted = await session.scalar(statement)
            if inserted is not None:
                started.append(run_id)
                try:
                    await self.execute_routine(run_id)
                except Exception as error:
                    await self._record_failure(run_id, error)
        return tuple(started)

    async def _record_failure(self, routine_run_id: UUID, error: Exception) -> None:
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            row = await session.get(RoutineRun, routine_run_id)
            if row is None:
                raise LookupError("Failed routine run disappeared") from error
            row.status = "failed"
            row.checkpoint = {**row.checkpoint, "stage": "failed", "error_type": type(error).__name__}
            session.add(AuditLog(
                tenant_id=self.tenant_id, workspace_id=self.workspace_id,
                actor_id=None, action="routine.failed", target_type="routine_run",
                target_id=routine_run_id, details={"error_type": type(error).__name__},
            ))
        await RuntimeEventEmitter(self._redis, self.tenant_id, self.workspace_id, routine_run_id).emit(
            RuntimeEventType.RUN_FAILED, {"error_type": type(error).__name__},
        )

    async def execute_routine(self, routine_run_id: UUID) -> str:
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            run = await session.scalar(select(RoutineRun).where(RoutineRun.id == routine_run_id).with_for_update())
            if run is None or not (
                run.status == "queued" or
                (run.status == "running" and run.checkpoint.get("stage") == "approved")
            ):
                raise LookupError("Executable routine run is not visible in this workspace")
            routine = await session.get(BotRoutine, run.routine_id)
            if routine is None:
                raise LookupError("Routine is not visible in this workspace")
            checkpoint = dict(run.checkpoint)
            run.status = "running"
            if checkpoint.get("stage") == "approved":
                run.checkpoint = {**checkpoint, "stage": "executing"}
            bot_id, workflow_id, instruction = routine.bot_id, routine.workflow_id, routine.instruction_markdown
        frontmatter, body = _parse_markdown(instruction)
        if not body:
            raise ValueError("Routine Markdown body cannot be empty")
        if checkpoint.get("stage") == "queued":
            await self._append(bot_id, routine_run_id, "user", body)
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                row = await session.get(RoutineRun, routine_run_id)
                if row is None:
                    raise LookupError("Routine run disappeared")
                row.checkpoint = {"stage": "prepared", "instruction": body}
        approval = frontmatter.get("approval")
        if approval is not None and checkpoint.get("stage") != "approved":
            if not isinstance(approval, dict) or approval.get("kind") not in ("external_email", "destructive_command", "high_spend"):
                raise ValueError("Routine approval front matter is invalid")
            if self._boundary_requester is None:
                raise PermissionError("Sensitive routine requires an approval coordinator")
            try:
                amount = Decimal(str(approval.get("amount_usd", "0")))
            except InvalidOperation as error:
                raise ValueError("Routine approval amount must be a decimal") from error
            if not amount.is_finite() or amount < 0:
                raise ValueError("Routine approval amount must be finite and nonnegative")
            if approval["kind"] == "high_spend" and "amount_usd" not in approval:
                raise ValueError("High-spend routine approval requires a nonnegative amount")
            intent = ActionIntent(approval["kind"], str(approval.get("description", body[:200])), amount)
            approval_id = await self._boundary_requester(routine_run_id, intent)
            if approval_id is not None:
                return "paused"
        try:
            result: str
            workflow_run_id: UUID | None
            if workflow_id is not None:
                state = await self.invoke_workflow(bot_id, workflow_id, body)
                result = state.status
                workflow_run_id = state.run_id
            else:
                bot = await self._bot(bot_id)
                result = await self._responder(bot, await self.history(bot_id, routine_run_id))
                await self._append(bot_id, routine_run_id, "assistant", result)
                workflow_run_id = None
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                row = await session.get(RoutineRun, routine_run_id)
                if row is None:
                    raise LookupError("Routine run disappeared")
                if result == "paused":
                    row.status = "paused"
                elif result == "failed":
                    row.status = "failed"
                else:
                    row.status = "completed"
                row.workflow_run_id = workflow_run_id
                row.checkpoint = {"stage": "waiting_workflow" if result == "paused" else "completed", "result": result}
            return result
        except Exception:
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                row = await session.get(RoutineRun, routine_run_id)
                if row is not None:
                    row.status = "failed"
                    row.checkpoint = {**row.checkpoint, "stage": "failed"}
            raise

    async def resume_routine(self, routine_run_id: UUID) -> str:
        async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
            row = await session.get(RoutineRun, routine_run_id)
            if row is None or row.status != "running":
                raise LookupError("Approved routine run is not visible in this workspace")
            workflow_run_id = row.workflow_run_id
            stage = row.checkpoint.get("stage")
        if stage == "waiting_workflow" and workflow_run_id is not None:
            state = await (await self.load_workflow(workflow_run_id)).resume()
            async with scoped_session(self._engine, self.tenant_id, self.workspace_id) as session:
                row = await session.get(RoutineRun, routine_run_id)
                if row is None:
                    raise LookupError("Routine run disappeared")
                row.status = "completed" if state.status == "completed" else state.status
                row.checkpoint = {"stage": state.status, "workflow_run_id": str(workflow_run_id)}
            return state.status
        return await self.execute_routine(routine_run_id)
