"""Phase 26: saved task conversations, readable failures, and retry."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.context import TenantContext
from app.models import AuditLog, ConversationMessage, RunCheckpoint, WorkflowRun
from app.models.scope import scoped_session
from app.routers import conversations, workflows
from checkpoints.failure import describe_failure, redact
from checkpoints.store import CheckpointStore
from flows.compiler import FlowCompiler
from flows.state import WorkflowState
from nexus_core_schema.artifacts import artifact_directory
from test_phase17_studio import TENANT, WORKSPACE, _Emitter, _FakeCrewBuilder, _MemoryCheckpoints, _gate_workflow


def test_failure_text_is_readable_but_never_carries_secrets_or_server_paths() -> None:
    raw = ("401 from https://api.example.com with Authorization: Bearer abcdef1234567890 and api_key=sk-live-0123456789abcdef; "
           "db postgresql+asyncpg://nexus:hunter2pw@postgres:5432/nexus at /workspace/apps/api/app/services.py line 4; token=eyJhbGciOiJI.eyJzdWIiOiIxMjM0.c2lnbmF0dXJlMTIzNDU2")
    clean = redact(raw)
    for leaked in ("abcdef1234567890", "sk-live-0123456789abcdef", "hunter2pw", "/workspace/apps/api", "eyJhbGciOiJI"):
        assert leaked not in clean, leaked
    assert "services.py" in clean and "401 from https://api.example.com" in clean

    try:
        raise ValueError("Crew did not return its required output (key sk-abcdefghijklmnop)")
    except ValueError as error:
        failure = describe_failure(error, node_id="story", node_label="Dept A")
    assert failure["failed_node_id"] == "story" and failure["failed_node_label"] == "Dept A" and failure["failed_agent_name"] is None
    assert failure["error_type"] == "ValueError" and "sk-abcdefghijklmnop" not in failure["error_message"]
    assert "test_phase26_history.py" in failure["traceback_summary"] and len(failure["error_message"]) <= 600


def test_a_failed_run_records_which_department_stopped_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    builder = _FakeCrewBuilder(artifact_directory(TENANT, WORKSPACE, run_id), {
        "build": lambda _attempt: {}, "qa": lambda _attempt: {}, "release": lambda _attempt: {},
    })
    checkpoints, emitter = _MemoryCheckpoints(), _Emitter(run_id)
    compiler = FlowCompiler(cast(Any, checkpoints), cast(Any, emitter), cast(Any, None), cast(Any, builder))
    with pytest.raises(ValueError):
        asyncio.run(compiler.compile(_gate_workflow(), run_id, {"task": "Make it"}).run())
    failure = checkpoints.failure
    assert failure is not None and failure["failed_node_id"] == "gate" and failure["error_type"] == "ValueError"
    assert "rework" in failure["error_message"]
    failed = [payload for kind, payload in emitter.events if kind == "RUN_FAILED"]
    assert failed and failed[0]["failure"]["failed_node_id"] == "gate" and failed[0]["message"].startswith(f"{failure['failed_node_label']}: ")


class _Redis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    async def get(self, key: str) -> str | None:
        return self.data.get(key)


class _Dispatcher:
    def __init__(self) -> None:
        self.queued: list[UUID] = []

    async def workflow(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        self.queued.append(run_id)


def _urls() -> tuple[str, str]:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL with the runtime role is required")
    return os.environ["NEXUS_TEST_DATABASE_URL"], os.environ["NEXUS_TEST_APP_DATABASE_URL"]


def test_threads_are_saved_isolated_retried_and_deleted_with_their_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url, app_url = _urls()
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))

    async def check() -> None:
        tenant, workspace, user, other_tenant, other_workspace = (uuid4() for _ in range(5))
        workflow_id, failed_run, running_run = uuid4(), uuid4(), uuid4()
        admin, runtime = create_async_engine(admin_url), create_async_engine(app_url)
        redis, dispatcher = _Redis(), _Dispatcher()
        services = SimpleNamespace(engine=runtime, dispatcher=dispatcher, checkpoints=CheckpointStore(runtime, cast(Any, redis)))
        request = cast(Request, SimpleNamespace(app=cast(FastAPI, SimpleNamespace(state=SimpleNamespace(services=services)))))
        owner = TenantContext(tenant, workspace, user, "owner")
        stranger = TenantContext(other_tenant, other_workspace, uuid4(), "owner")
        try:
            async with admin.begin() as connection:
                for t, w in ((tenant, workspace), (other_tenant, other_workspace)):
                    await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'History')"), {"id": t})
                    await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'History')"), {"id": w, "t": t})
                await connection.execute(text("INSERT INTO users (id, tenant_id, workspace_id, email, password_hash, display_name) VALUES (:u, :t, :w, :e, 'x', 'Owner')"),
                                         {"u": user, "t": tenant, "w": workspace, "e": f"history-{user}@example.invalid"})
                await connection.execute(text("INSERT INTO workflows (id, tenant_id, workspace_id, name, version, spec) VALUES (:id, :t, :w, 'Team', 1, '{}'::jsonb)"),
                                         {"id": workflow_id, "t": tenant, "w": workspace})
            state = WorkflowState(id=failed_run, run_id=failed_run, workflow_id=workflow_id, tenant_id=tenant, workspace_id=workspace, status="running",
                                  input_data={"task": "make a film"}, completed_nodes=["start", "story"], node_outputs={"start": {}, "story": {"summary": "ok"}})
            async with scoped_session(runtime, tenant, workspace) as session:
                for run, status in ((failed_run, "queued"), (running_run, "running")):
                    session.add(WorkflowRun(id=run, tenant_id=tenant, workspace_id=workspace, workflow_id=workflow_id, status=status, input_data={"task": "make a film"}))
                conversation = await conversations.start_conversation(session, owner, "make a film")
                await conversations.append_message(session, conversation, "user", "make a film")
                await conversations.append_message(session, conversation, "team", "A team of 6", run_id=failed_run, workflow_id=workflow_id)
                other = await conversations.start_conversation(session, owner, "second thread")
                await conversations.append_message(session, other, "team", "Running team", run_id=running_run, workflow_id=workflow_id)
            await services.checkpoints.save(state)
            await services.checkpoints.save(state.model_copy(update={"status": "failed"}))
            await services.checkpoints.record_failure(state, describe_failure(ValueError("boom"), node_id="art", node_label="Dept C"))
            directory = artifact_directory(tenant, workspace, failed_run)
            directory.mkdir(parents=True)
            (directory / "story.md").write_text("draft")

            # The thread comes back whole, in order, and only to its own workspace.
            thread = await conversations.get_conversation(conversation.id, request, owner)
            assert [(m["role"], m["text"]) for m in thread["messages"]] == [("user", "make a film"), ("team", "A team of 6")]
            assert thread["messages"][1]["run_id"] == str(failed_run)
            with pytest.raises(HTTPException) as hidden:
                await conversations.get_conversation(conversation.id, request, stranger)
            assert hidden.value.status_code == 404
            note = await conversations.add_note(conversation.id, conversations.NoteWrite(text="Saved story.md"), request, owner)
            assert note["sequence"] == 3 and note["role"] == "note"
            assert {item["id"] for item in await conversations.list_conversations(request, owner)} == {str(conversation.id), str(other.id)}

            # Runs say which thread they belong to and why they failed.
            listed = {item["id"]: item for item in await workflows.list_runs(request, owner)}
            assert listed[str(failed_run)]["conversation_id"] == str(conversation.id) and listed[str(failed_run)]["failure"]["failed_node_id"] == "art"
            detail = cast(dict[str, Any], await workflows.get_run(failed_run, request, owner))
            assert detail["failure"]["error_type"] == "ValueError" and detail["conversation_id"] == str(conversation.id)

            # Retrying a step continues the same run from its checkpoint and forgets the old failure.
            assert (await workflows.retry_run(failed_run, workflows.RetryRequest(mode="step"), request, owner))["mode"] == "step"
            assert dispatcher.queued == [failed_run]
            after = cast(dict[str, Any], await workflows.get_run(failed_run, request, owner))
            assert after["status"] == "running" and after["failure"] is None
            resumed = await services.checkpoints.load(tenant, workspace, failed_run)
            assert resumed.status == "running" and resumed.completed_nodes == ["start", "story"], "finished departments are kept"
            with pytest.raises(HTTPException) as busy:
                await workflows.retry_run(failed_run, workflows.RetryRequest(mode="step"), request, owner)
            assert busy.value.status_code == 409

            # Retrying the team starts a fresh run in the same thread.
            await services.checkpoints.save(resumed.model_copy(update={"status": "failed"}))
            started = await workflows.retry_run(failed_run, workflows.RetryRequest(mode="team"), request, owner)
            new_run = UUID(started["run_id"])
            assert started["mode"] == "team" and new_run != failed_run and dispatcher.queued[-1] == new_run
            thread = await conversations.get_conversation(conversation.id, request, owner)
            assert thread["messages"][-1]["run_id"] == str(new_run) and thread["messages"][-1]["meta"]["retry_of"] == str(failed_run)

            # A task that is still running is not deleted; a finished one goes with its files, the audit trail stays.
            with pytest.raises(HTTPException) as running:
                await conversations.delete_conversation(other.id, request, owner)
            assert running.value.status_code == 409
            async with scoped_session(runtime, tenant, workspace) as session:
                (await session.get(WorkflowRun, new_run)).status = "failed"  # type: ignore[union-attr]
            await conversations.delete_conversation(conversation.id, request, owner)
            assert not directory.exists()
            async with scoped_session(runtime, tenant, workspace) as session:
                assert await session.get(WorkflowRun, failed_run) is None and await session.get(WorkflowRun, new_run) is None
                assert (await session.scalars(select(RunCheckpoint).where(RunCheckpoint.run_id == failed_run))).first() is None
                assert (await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation.id))).first() is None
                assert await session.get(WorkflowRun, running_run) is not None
                assert (await session.scalars(select(AuditLog).where(AuditLog.action == "conversation.deleted"))).first() is not None
        finally:
            await admin.dispose()
            await runtime.dispose()

    asyncio.run(check())


def test_a_second_similar_request_gets_a_free_workflow_name_instead_of_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers.architect import free_workflow_name
    from app.models import Workflow

    admin_url, app_url = _urls()

    async def check() -> None:
        tenant, workspace = uuid4(), uuid4()
        admin, runtime = create_async_engine(admin_url), create_async_engine(app_url)
        try:
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Names')"), {"id": tenant})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'Names')"), {"id": workspace, "t": tenant})
            async with scoped_session(runtime, tenant, workspace) as session:
                assert await free_workflow_name(session, "Coffee shop launch", 1) == "Coffee shop launch"
                for name in ("Coffee shop launch", "Coffee shop launch (2)", "100%_sure"):
                    session.add(Workflow(id=uuid4(), tenant_id=tenant, workspace_id=workspace, name=name, version=1, spec={}))
                await session.flush()
                assert await free_workflow_name(session, "Coffee shop launch", 1) == "Coffee shop launch (3)"
                assert await free_workflow_name(session, "Coffee shop launch", 2) == "Coffee shop launch", "another version is a different workflow"
                assert await free_workflow_name(session, "100%_sure", 1) == "100%_sure (2)", "% and _ in a name are not wildcards"
                assert await free_workflow_name(session, "Coffee", 1) == "Coffee"
        finally:
            await admin.dispose()
            await runtime.dispose()

    asyncio.run(check())
