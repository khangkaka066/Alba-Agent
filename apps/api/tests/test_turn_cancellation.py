"""User stops are scoped, block future work and retain the last safe output."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request

from app.auth.context import TenantContext
from app.routers import workflows
from app.workers import jobs
from checkpoints.store import CheckpointStore, RunCancelled
from flows.state import WorkflowState


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, **kwargs: Any) -> None:
        self.values[key] = value


def test_cancellation_blocks_checkpoint_writes_only_in_its_own_scope() -> None:
    tenant, workspace, run = uuid4(), uuid4(), uuid4()
    redis = MemoryRedis()
    store = CheckpointStore(cast(Any, None), cast(Any, redis))
    state = WorkflowState(id=run, run_id=run, tenant_id=tenant, workspace_id=workspace, workflow_id=uuid4(), status="running", node_outputs={"draft": {"answer": "Partial result"}})

    async def check() -> None:
        await redis.set(store.cancellation_key(tenant, workspace, run), "1")
        with pytest.raises(RunCancelled) as stopped:
            await store.save(state)  # The fake engine cannot be reached; cancellation must precede writes.
        assert stopped.value.state is state
        await store.assert_running(tenant, uuid4(), run)
        await store.assert_running(uuid4(), workspace, run)
    asyncio.run(check())


@pytest.mark.parametrize(("status", "expected"), [("queued", "cancelled"), ("paused", "cancelled"), ("running", "cancelling"), ("completed", "completed")])
def test_cancel_route_stops_only_a_visible_run(monkeypatch: pytest.MonkeyPatch, status: str, expected: str) -> None:
    context = TenantContext(uuid4(), uuid4(), uuid4(), "owner")
    run = SimpleNamespace(id=uuid4(), status=status, finished_at=None)
    redis = MemoryRedis()
    events: list[dict[str, Any]] = []
    audits: list[Any] = []

    class Session:
        async def scalar(self, statement: Any) -> Any:
            return run
        def add(self, row: Any) -> None:
            audits.append(row)

    @asynccontextmanager
    async def session(*args: Any) -> AsyncIterator[Session]:
        assert args[1:] == (context.tenant_id, context.workspace_id)
        yield Session()

    class Emitter:
        def __init__(self, *args: Any) -> None:
            assert args[1:] == (context.tenant_id, context.workspace_id, run.id)
        async def emit(self, event: Any, payload: dict[str, Any]) -> None:
            events.append(payload)

    monkeypatch.setattr(workflows, 'scoped_session', session)
    monkeypatch.setattr(workflows, 'RuntimeEventEmitter', Emitter)
    app = FastAPI(); app.state.services = SimpleNamespace(engine=None, redis=redis)
    response = asyncio.run(workflows.cancel_run(run.id, Request({'type': 'http', 'app': app}), context))
    assert response == {'status': expected}
    assert run.status == ('cancelled' if status in ('queued', 'paused') else status)
    if status != 'completed':
        assert redis.values == {CheckpointStore.cancellation_key(context.tenant_id, context.workspace_id, run.id): '1'}
        assert events == [{'status': expected, 'reason': 'user_requested'}]
        assert len(audits) == 1
    else:
        assert not redis.values and not events and not audits


def test_worker_acknowledges_a_stop_without_reporting_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant, workspace, run = uuid4(), uuid4(), uuid4()
    state = WorkflowState(id=run, run_id=run, tenant_id=tenant, workspace_id=workspace, workflow_id=uuid4(), status='running', node_outputs={'draft': {'answer': 'Saved draft'}})
    saved: list[WorkflowState] = []
    retired: list[Any] = []
    events: list[dict[str, Any]] = []
    row = SimpleNamespace(id=run, status='queued', workflow_id=state.workflow_id, input_data={}, started_at=None)
    class Session:
        async def scalar(self, statement: Any) -> Any:
            return row
        def add(self, record: Any) -> None:
            return None
    @asynccontextmanager
    async def session(*args: Any) -> AsyncIterator[Session]:
        yield Session()
    class Compiled:
        async def resume_execution(self) -> WorkflowState:
            raise RunCancelled(state)
    class Emitter:
        def __init__(self, *args: Any) -> None:
            return None
        async def emit(self, event: Any, payload: dict[str, Any]) -> None:
            events.append(payload)
    async def compiled(*args: Any) -> Compiled:
        return Compiled()
    async def save(value: WorkflowState) -> None:
        saved.append(value)
    async def retire(*args: Any) -> None:
        retired.append(args)
    async def reap() -> None:
        return None
    services = SimpleNamespace(engine=None, redis=None, sandbox=SimpleNamespace(reap_orphans=reap), checkpoints=SimpleNamespace(save=save), compiled_workflow=compiled, _after_run=retire)
    monkeypatch.setattr(jobs, 'scoped_session', session)
    monkeypatch.setattr(jobs, 'RuntimeEventEmitter', Emitter)
    result = asyncio.run(jobs.WorkerExecutor(cast(Any, services)).workflow(tenant, workspace, run))
    assert result == 'cancelled'
    assert saved[0].node_outputs == {'draft': {'answer': 'Saved draft'}}
    assert saved[0].active_node_id is None and saved[0].status == 'cancelled'
    assert retired == [(tenant, workspace, run)]
    assert events == [{'status': 'cancelled', 'reason': 'user_requested'}]


def test_cancel_route_refuses_invisible_run_without_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    context = TenantContext(uuid4(), uuid4(), uuid4(), 'owner')
    redis = MemoryRedis()
    class Session:
        async def scalar(self, statement: Any) -> None:
            return None
    @asynccontextmanager
    async def session(*args: Any) -> AsyncIterator[Session]:
        yield Session()
    monkeypatch.setattr(workflows, 'scoped_session', session)
    app = FastAPI(); app.state.services = SimpleNamespace(engine=None, redis=redis)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(workflows.cancel_run(uuid4(), Request({'type': 'http', 'app': app}), context))
    assert refused.value.status_code == 404 and not redis.values


def test_cancelled_database_state_cannot_be_overwritten_after_the_signal_expires() -> None:
    run_id = uuid4()
    state = WorkflowState(id=run_id, run_id=run_id, tenant_id=uuid4(), workspace_id=uuid4(), workflow_id=uuid4(), status='completed')
    row = SimpleNamespace(status='cancelled')
    with pytest.raises(RunCancelled):
        asyncio.run(CheckpointStore._append_checkpoint(cast(Any, None), cast(Any, row), state))
