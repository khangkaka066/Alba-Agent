"""Redis-backed Celery tasks for workflows, bot turns, and routine schedules."""

from __future__ import annotations

import asyncio
import atexit
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import worker_process_shutdown  # type: ignore[import-untyped]
from sqlalchemy import select

from app.models import AuditLog, ModelCredential, RunCheckpoint, WorkflowRun
from app.models.scope import scoped_session
from app.services import AppServices, TaskDispatcher, create_default_services
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.failure import describe_failure, is_model_not_found, with_model_suggestions
from checkpoints.store import RunCancelled
from flows.compiler import public_error
from flows.state import WorkflowState
from nexus_core_schema.models import RuntimeEventType


def _redis_url() -> str:
    override = os.environ.get("NEXUS_REDIS_URL")
    if override:
        return override
    password = quote(os.environ.get("NEXUS_REDIS_PASSWORD", ""), safe="")
    host = os.environ.get("NEXUS_REDIS_HOST", "redis")
    port = int(os.environ.get("NEXUS_REDIS_PORT", "6379"))
    return f"redis://:{password}@{host}:{port}/0"


celery_app = Celery("nexus_agent_studio", broker=_redis_url())
logger = logging.getLogger(__name__)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=21600,
    task_soft_time_limit=21000,
    broker_transport_options={"global_keyprefix": "nexus_celery:", "visibility_timeout": 21600},
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "nexus-routine-scan": {"task": "nexus.scan_routines", "schedule": 60.0},
    },
)


class _WorkerDispatcher:
    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def workflow(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        return None

    async def bot_turn(self, tenant_id: UUID, workspace_id: UUID, bot_id: UUID, thread_id: UUID, content: str) -> None:
        return None

    async def routine(self, tenant_id: UUID, workspace_id: UUID, routine_run_id: UUID) -> None:
        return None


class WorkerExecutor:
    def __init__(self, services: AppServices) -> None:
        self.services = services

    async def workflow(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> str:
        try:
            # Containers left by a crashed worker are found by their labels; this runs before each run so no scheduler is needed.
            await self.services.sandbox.reap_orphans()
        except Exception:
            logging.getLogger("nexus.sandbox").exception("Stale sandbox computers could not be reaped")
        async with scoped_session(self.services.engine, tenant_id, workspace_id) as session:
            run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
            if run is None:
                raise LookupError("Queued workflow is not visible in this workspace")
            if run.status != "queued":
                if run.status != "running":
                    return run.status
                has_checkpoint = await session.scalar(select(RunCheckpoint.id).where(RunCheckpoint.run_id == run_id).limit(1)) is not None
            else:
                initial = WorkflowState(
                    id=run_id, run_id=run_id, workflow_id=run.workflow_id,
                    tenant_id=tenant_id, workspace_id=workspace_id,
                    input_data=cast(dict[str, Any], dict(run.input_data)), status="running",
                    upstream_artifacts=cast(list[dict[str, Any]], list(cast(dict[str, Any], run.input_data).get("upstream_artifacts", []))),
                )
                initial.sequence = 1
                session.add(RunCheckpoint(
                    tenant_id=tenant_id, workspace_id=workspace_id, run_id=run_id,
                    sequence=1, state=initial.model_dump(mode="json"),
                ))
                run.started_at = datetime.now(timezone.utc)
                has_checkpoint = True
            run.status = "running"
            input_data = cast(dict[str, Any], dict(run.input_data))
        try:
            compiled = await self.services.compiled_workflow(tenant_id, workspace_id, run_id, input_data)
            state = await compiled.resume_execution() if has_checkpoint else await compiled.run_precreated()
            await self.services.checkpoints.assert_running(tenant_id, workspace_id, run_id, state)
            await self._monitor_distillation(tenant_id, workspace_id, run_id)
            await self.services._after_run(tenant_id, workspace_id, run_id)
            return state.status
        except RunCancelled as stopped:
            state = stopped.state or await self.services.checkpoints.load(tenant_id, workspace_id, run_id)
            state.status = "cancelled"
            state.active_node_id = None
            state.pending_approval_id = None
            await self.services.checkpoints.save(state)
            await RuntimeEventEmitter(self.services.redis, tenant_id, workspace_id, run_id).emit(
                RuntimeEventType.FLOW_STATE_CHANGED, {"status": "cancelled", "reason": "user_requested"},
            )
            await self.services._after_run(tenant_id, workspace_id, run_id)
            return state.status
        except Exception as error:
            async with scoped_session(self.services.engine, tenant_id, workspace_id) as session:
                run = await session.get(WorkflowRun, run_id)
                if run is not None and run.status not in ("failed", "completed", "paused"):
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    failure = describe_failure(error)
                    if is_model_not_found(error):
                        from app.routers.architect import trusted_default_models
                        connected = (await session.scalars(select(ModelCredential).where(ModelCredential.status == "connected"))).all()
                        known = {f"{row.provider}/{model}" for row in connected for model in row.available_models}
                        failure = with_model_suggestions(failure, trusted_default_models(connected, known))
                    run.failure = failure
                    session.add(AuditLog(
                        tenant_id=tenant_id, workspace_id=workspace_id,
                        actor_id=None, action="workflow.failed", target_type="workflow_run",
                        target_id=run_id, details={"error_type": type(error).__name__, "message": public_error(error)},
                    ))
            await self._monitor_distillation(tenant_id, workspace_id, run_id)
            await self.services._after_run(tenant_id, workspace_id, run_id)
            await RuntimeEventEmitter(self.services.redis, tenant_id, workspace_id, run_id).emit(
                RuntimeEventType.RUN_FAILED,
                {"error_type": type(error).__name__, "message": public_error(error)},
            )
            raise

    async def _monitor_distillation(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        from app.finops import monitor_live_distillation

        try:
            await monitor_live_distillation(self.services, tenant_id, workspace_id, run_id)
        except Exception:
            logger.exception("FinOps model monitor could not evaluate a run", extra={"run_id": str(run_id)})

    async def bot_turn(self, tenant_id: UUID, workspace_id: UUID, bot_id: UUID, thread_id: UUID, content: str) -> str:
        return await self.services.bot_runner(tenant_id, workspace_id).chat(bot_id, thread_id, content)

    async def routine(self, tenant_id: UUID, workspace_id: UUID, routine_run_id: UUID) -> str:
        return await self.services.bot_runner(tenant_id, workspace_id).execute_routine(routine_run_id)

    async def scan_routines(self) -> dict[str, int]:
        scopes: list[tuple[UUID, UUID]] = []
        async for key in self.services.redis.scan_iter(match="nexus:*:scheduler:workspaces"):
            tenant_text = str(key).split(":", 2)[1]
            values = cast(Any, self.services.redis.smembers(key))
            for workspace in await values:
                scopes.append((UUID(tenant_text), UUID(str(workspace))))
        results: dict[str, int] = {}
        for tenant_id, workspace_id in scopes:
            due = await self.services.bot_runner(tenant_id, workspace_id).run_due(datetime.now(timezone.utc))
            results[f"{tenant_id}:{workspace_id}"] = len(due)
        return results


async def _run_task(operation: str, identifiers: tuple[str, ...], content: str | None = None, provided: AppServices | None = None) -> str | dict[str, int]:
    services = provided or await create_default_services(_WorkerDispatcher())
    executor = WorkerExecutor(services)
    try:
        if operation == "workflow":
            return await executor.workflow(UUID(identifiers[0]), UUID(identifiers[1]), UUID(identifiers[2]))
        if operation == "bot_turn":
            if content is None:
                raise ValueError("Bot turn content is missing")
            return await executor.bot_turn(UUID(identifiers[0]), UUID(identifiers[1]), UUID(identifiers[2]), UUID(identifiers[3]), content)
        if operation == "routine":
            return await executor.routine(UUID(identifiers[0]), UUID(identifiers[1]), UUID(identifiers[2]))
        if operation == "scan_routines":
            return await executor.scan_routines()
        raise ValueError("Unknown worker operation")
    finally:
        if provided is None:
            await services.shutdown()


class _WorkerRuntime:
    """A Celery process owns one live loop; PTYs and previews keep running between jobs."""

    def __init__(self, factory: Callable[[], Awaitable[AppServices]] | None = None) -> None:
        self.pid = os.getpid()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._serve, name="nexus-worker-runtime", daemon=True)
        self.thread.start()
        async def boot() -> AppServices:
            return await factory() if factory is not None else await create_default_services(_WorkerDispatcher())
        try:
            self.services = asyncio.run_coroutine_threadsafe(boot(), self.loop).result(timeout=120)
        except BaseException:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=10)
            raise

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            remaining = asyncio.all_tasks(self.loop)
            for task in remaining:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*remaining, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()

    def run(self, operation: str, identifiers: tuple[str, ...], content: str | None = None) -> str | dict[str, int]:
        return asyncio.run_coroutine_threadsafe(_run_task(operation, identifiers, content, self.services), self.loop).result()

    def close(self) -> None:
        if not self.thread.is_alive():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.services.shutdown(), self.loop).result(timeout=20)
        except Exception:
            logging.getLogger("nexus.worker").exception("Worker services could not finish shutting down")
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=20)


_worker_runtime: _WorkerRuntime | None = None
_worker_runtime_lock = threading.Lock()


def _close_worker_runtime(**_kwargs: Any) -> None:
    global _worker_runtime
    with _worker_runtime_lock:
        runtime, _worker_runtime = _worker_runtime, None
    if runtime is not None and runtime.pid == os.getpid():
        runtime.close()


worker_process_shutdown.connect(_close_worker_runtime, weak=False)
atexit.register(_close_worker_runtime)


def _run_sync(operation: str, identifiers: tuple[str, ...], content: str | None = None) -> str | dict[str, int]:
    global _worker_runtime
    with _worker_runtime_lock:
        if _worker_runtime is None or _worker_runtime.pid != os.getpid():
            _worker_runtime = _WorkerRuntime()
        runtime = _worker_runtime
    return runtime.run(operation, identifiers, content)


@celery_app.task(name="nexus.run_workflow", acks_late=True)  # type: ignore[misc]
def run_workflow_task(tenant_id: str, workspace_id: str, run_id: str) -> str:
    return cast(str, _run_sync("workflow", (tenant_id, workspace_id, run_id)))


@celery_app.task(name="nexus.bot_turn", acks_late=True)  # type: ignore[misc]
def bot_turn_task(tenant_id: str, workspace_id: str, bot_id: str, thread_id: str, content: str) -> str:
    return cast(str, _run_sync("bot_turn", (tenant_id, workspace_id, bot_id, thread_id), content))


@celery_app.task(name="nexus.routine", acks_late=True)  # type: ignore[misc]
def routine_task(tenant_id: str, workspace_id: str, routine_run_id: str) -> str:
    return cast(str, _run_sync("routine", (tenant_id, workspace_id, routine_run_id)))


@celery_app.task(name="nexus.scan_routines", acks_late=True)  # type: ignore[misc]
def scan_routines_task() -> dict[str, int]:
    return cast(dict[str, int], _run_sync("scan_routines", ()))


class CeleryDispatcher(TaskDispatcher):
    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def workflow(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        await asyncio.to_thread(celery_app.send_task, "nexus.run_workflow", args=[str(tenant_id), str(workspace_id), str(run_id)])

    async def bot_turn(self, tenant_id: UUID, workspace_id: UUID, bot_id: UUID, thread_id: UUID, content: str) -> None:
        await asyncio.to_thread(celery_app.send_task, "nexus.bot_turn", args=[str(tenant_id), str(workspace_id), str(bot_id), str(thread_id), content])

    async def routine(self, tenant_id: UUID, workspace_id: UUID, routine_run_id: UUID) -> None:
        await asyncio.to_thread(celery_app.send_task, "nexus.routine", args=[str(tenant_id), str(workspace_id), str(routine_run_id)])
