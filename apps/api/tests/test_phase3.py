from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import rmtree
from uuid import UUID, uuid4

import pytest
from autogen_core import FunctionCall
from autogen_core.models import CreateResult, ModelFamily, ModelInfo, RequestUsage
from autogen_ext.models.replay import ReplayChatCompletionClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from autogen_bridge.sandbox_team import AutoGenSandboxRunner
from bots.runner import BotRunner, cron_matches
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.approval import ActionIntent, ApprovalCoordinator, BoundaryPolicy
from checkpoints.store import CheckpointStore
from flows.compiler import PauseRequested
from flows.state import WorkflowState
from nexus_computer_sandbox import ComputerAccess, ComputerSandboxSupervisor, DockerSandboxProvider
from nexus_core_schema.models import PersistentBotSpec, RuntimeEvent, RuntimeEventType, WorkflowSpec
from app.workers.routine_scheduler import RoutineScheduler


def _require_services() -> None:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL", "NEXUS_TEST_REDIS_URL", "NEXUS_SANDBOX_TEST_ROOT")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL, Redis, and host-shared Docker root are required")


def test_cron_matches_timezone_and_interval_fields() -> None:
    moment = datetime(2026, 10, 30, 2, 15, tzinfo=timezone.utc)
    assert cron_matches("15 9 * * 5", moment, "Asia/Ho_Chi_Minh")
    assert not cron_matches("0 9 * * 5", moment, "Asia/Ho_Chi_Minh")
    assert cron_matches("*/5 9 * * *", moment, "Asia/Ho_Chi_Minh")
    with pytest.raises(ValueError):
        cron_matches("bad", moment, "UTC")
    policy = BoundaryPolicy()
    assert policy.requires_approval(ActionIntent("external_email", "Send message"))
    assert policy.requires_approval(ActionIntent("destructive_command", "Remove files"))
    assert not policy.requires_approval(ActionIntent("high_spend", "Small request"))


def test_persistent_computer_lifecycle_and_agent_bridge() -> None:
    _require_services()

    async def check() -> None:
        tenant_id, workspace_id, run_id = uuid4(), uuid4(), uuid4()
        admin = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"])
        app = create_async_engine(os.environ["NEXUS_TEST_APP_DATABASE_URL"])
        redis = Redis.from_url(os.environ["NEXUS_TEST_REDIS_URL"], decode_responses=True)
        root = Path(os.environ["NEXUS_SANDBOX_TEST_ROOT"])
        root.mkdir(parents=True, exist_ok=True)
        try:
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Computer test')"), {"id": tenant_id})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :tenant, 'Computer test')"), {"id": workspace_id, "tenant": tenant_id})

            frame = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=")

            async def browser_hook(_handle: object, _action: str, _arguments: dict[str, str]) -> bytes:
                return frame

            supervisor = ComputerSandboxSupervisor(app, DockerSandboxProvider(root), browser_hook=browser_hook)
            access = ComputerAccess(tenant_id, workspace_id, run_id=run_id)
            shared = await supervisor.create(ComputerAccess(tenant_id, workspace_id), "shared")
            private = await supervisor.create(access)
            assert (await supervisor.get(ComputerAccess(tenant_id, workspace_id), shared.id)).id == shared.id
            with pytest.raises(PermissionError):
                await supervisor.get(ComputerAccess(tenant_id, workspace_id, run_id=uuid4()), private.id)
            with pytest.raises(LookupError):
                await supervisor.get(ComputerAccess(tenant_id, uuid4(), run_id=run_id), private.id)
            await supervisor.upload(access, private.id, "input.txt", b"7\n")
            assert await supervisor.download(access, private.id, "input.txt") == b"7\n"
            with pytest.raises(ValueError):
                await supervisor.upload(access, private.id, "../escape.txt", b"bad")

            output: list[str] = []

            async def sink(stream: str, content: str) -> None:
                output.append(f"{stream}:{content}")

            result = await supervisor.execute_shell(access, private.id, "cat input.txt", 30, sink)
            assert result.exit_code == 0 and result.stdout.strip() == "7"
            assert output
            assert (await supervisor.execute_shell(access, private.id, "sleep 2", 1, sink)).exit_code != 0
            assert (await supervisor.execute_shell(access, private.id, "cat input.txt", 30, sink)).exit_code == 0
            await supervisor.execute_shell(access, private.id, "ln -s /etc/passwd link.txt", 30, sink)
            with pytest.raises(OSError):
                await supervisor.download(access, private.id, "link.txt")
            with pytest.raises(PermissionError):
                await supervisor.execute_shell(access, private.id, "rm input.txt", 30, sink, boundary="destructive_command")
            with pytest.raises(PermissionError):
                await supervisor.browser_action(access, private.id, "send_email", {})
            assert await supervisor.browser_action(access, private.id, "screenshot", {}) == frame
            stream = supervisor.screen_proxy(access, private.id)
            assert await asyncio.wait_for(anext(stream), 2) == frame
            await stream.aclose()
            emitter = RuntimeEventEmitter(redis, tenant_id, workspace_id, run_id)
            pubsub = redis.pubsub()
            await pubsub.subscribe(emitter.channel)
            await pubsub.get_message(timeout=1)
            screen_task = asyncio.create_task(supervisor.stream_screen_events(access, private.id, emitter))
            try:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
                assert message is not None
                event = RuntimeEvent.model_validate_json(message["data"])
                assert event.type == RuntimeEventType.SANDBOX_SCREEN_FRAME
                assert base64.b64decode(event.payload["data_base64"]) == frame
            finally:
                screen_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await screen_task
                await pubsub.aclose()

            code = "value = int(open('dataset.csv').read().splitlines()[1])\nopen('result.txt', 'w').write(str(value))\nprint('done')"
            model_info: ModelInfo = {
                "vision": False, "function_calling": True, "json_output": False,
                "family": ModelFamily.UNKNOWN, "structured_output": False,
            }

            def client_factory(model: str) -> ReplayChatCompletionClient:
                if model == "coder-model":
                    response = CreateResult(
                        finish_reason="function_calls",
                        content=[FunctionCall(id="execute-1", name="execute_python", arguments=json.dumps({"code": code}))],
                        usage=RequestUsage(prompt_tokens=3, completion_tokens=3), cached=False,
                    )
                    return ReplayChatCompletionClient([response], model_info=model_info)
                return ReplayChatCompletionClient(["APPROVED. Verified six."])

            from nexus_core_schema.models import AutoGenSandboxNodeSpec

            spec = AutoGenSandboxNodeSpec(
                id="compute", label="Compute", coder_model="coder-model", reviewer_model="reviewer-model",
                verification_command="python -c \"assert open('result.txt').read() == '6'\"",
                max_rounds=2, timeout_seconds=30,
            )
            result2 = await AutoGenSandboxRunner(supervisor, client_factory).run(
                "Write sum to result.txt", spec, RuntimeEventEmitter(redis, tenant_id, workspace_id, run_id),
                input_files={"dataset.csv": b"value\n6\n"},
            )
            assert result2.exit_code == 0
            assert "result.txt" in result2.artifacts
            assert await supervisor.download(access, private.id, "dataset.csv") == b"value\n6\n"
            assert await supervisor.download(access, private.id, "result.txt") == b"6"
            await supervisor.terminate(access, private.id)
            await supervisor.terminate(ComputerAccess(tenant_id, workspace_id), shared.id)
            async with admin.connect() as connection:
                count = await connection.scalar(text("SELECT count(*) FROM audit_logs WHERE tenant_id=:tenant AND action='computer.shell'"), {"tenant": tenant_id})
                assert count is not None and count >= 2
        finally:
            await redis.aclose()
            await app.dispose()
            await admin.dispose()
            scoped_root = root / str(tenant_id)
            if scoped_root.exists():
                rmtree(scoped_root)

    asyncio.run(check())


def test_bot_routine_approval_resume_and_audit() -> None:
    _require_services()

    async def check() -> None:
        tenant_id, workspace_id, bot_id, routine_id, workflow_id, user_id = (uuid4() for _ in range(6))
        admin = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"])
        app = create_async_engine(os.environ["NEXUS_TEST_APP_DATABASE_URL"])
        redis = Redis.from_url(os.environ["NEXUS_TEST_REDIS_URL"], decode_responses=True)
        root = Path(os.environ["NEXUS_SANDBOX_TEST_ROOT"])
        try:
            bot_spec = PersistentBotSpec(
                id=bot_id, tenant_id=tenant_id, workspace_id=workspace_id,
                name="Analyst", model="local", memory_namespace="bot-memory",
            )
            workflow_spec = WorkflowSpec.model_validate({
                "id": str(workflow_id), "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
                "name": "Reviewed task", "version": 1,
                "nodes": [
                    {"id": "start", "kind": "start"},
                    {"id": "approval", "kind": "approval", "label": "Review", "action_description": "Publish result"},
                ],
                "edges": [{"source": "start", "target": "approval"}],
            })
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Bot test')"), {"id": tenant_id})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :tenant, 'Bot test')"), {"id": workspace_id, "tenant": tenant_id})
                await connection.execute(text("INSERT INTO users (id, tenant_id, workspace_id, email, password_hash, display_name) VALUES (:id,:tenant,:workspace,'approver@example.invalid','test','Approver')"), {"id": user_id, "tenant": tenant_id, "workspace": workspace_id})
                await connection.execute(text("INSERT INTO workspace_members (id,tenant_id,workspace_id,user_id,role) VALUES (:id,:tenant,:workspace,:user,'admin')"), {"id": uuid4(), "tenant": tenant_id, "workspace": workspace_id, "user": user_id})
                await connection.execute(text("INSERT INTO persistent_bots (id,tenant_id,workspace_id,name,model,spec) VALUES (:id,:tenant,:workspace,'Analyst','local',CAST(:spec AS jsonb))"), {"id": bot_id, "tenant": tenant_id, "workspace": workspace_id, "spec": bot_spec.model_dump_json()})
                await connection.execute(text("INSERT INTO workflows (id,tenant_id,workspace_id,name,version,spec) VALUES (:id,:tenant,:workspace,'Reviewed task',1,CAST(:spec AS jsonb))"), {"id": workflow_id, "tenant": tenant_id, "workspace": workspace_id, "spec": workflow_spec.model_dump_json()})
                await connection.execute(text("INSERT INTO bot_routines (id,tenant_id,workspace_id,bot_id,name,instruction_markdown,cron_expression,timezone,enabled,interval_seconds) VALUES (:id,:tenant,:workspace,:bot,'Morning summary',:markdown,'* * * * *','UTC',true,60)"), {
                    "id": routine_id, "tenant": tenant_id, "workspace": workspace_id, "bot": bot_id,
                    "markdown": "---\napproval:\n  kind: external_email\n  description: Send daily summary\n---\n# Daily summary\nPrepare a summary.",
                })

            async def responder(_bot: PersistentBotSpec, messages: tuple[tuple[str, str], ...]) -> str:
                return f"Handled {messages[-1][1]}"

            coordinator: ApprovalCoordinator

            async def request(run_id: UUID, intent: ActionIntent) -> UUID | None:
                return await coordinator.pause_routine_for_action(run_id, intent)

            runner = BotRunner(
                app, redis, tenant_id, workspace_id, responder,
                AutoGenSandboxRunner(ComputerSandboxSupervisor(app, DockerSandboxProvider(root)), lambda _: ReplayChatCompletionClient(["unused"])),
                boundary_requester=request,
            )
            coordinator = ApprovalCoordinator(
                app, redis, CheckpointStore(app, redis), tenant_id, workspace_id,
                user_id, runner.load_workflow, runner.resume_routine,
            )
            thread_id = uuid4()
            assert (await runner.chat(bot_id, thread_id, "Hello")).startswith("Handled")
            assert len(await runner.history(bot_id, thread_id)) == 2
            first_time = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)
            async def scopes() -> tuple[tuple[UUID, UUID], ...]:
                return ((tenant_id, workspace_id),)

            scheduler = RoutineScheduler(scopes, lambda _tenant, _workspace: runner)
            first = (await scheduler.run_once(first_time))[(tenant_id, workspace_id)][0]
            assert (await scheduler.run_once(first_time))[(tenant_id, workspace_id)] == ()
            async with admin.connect() as connection:
                status = await connection.scalar(text("SELECT status FROM routine_runs WHERE id=:id"), {"id": first})
                assert status == "paused"
            assert await coordinator.resume_from_approval(first, "allow_once") == "Handled # Daily summary\nPrepare a summary."
            second = (await runner.run_due(first_time + timedelta(seconds=61)))[0]
            assert await coordinator.resume_from_approval(second, "always_allow_routine")
            third = (await runner.run_due(first_time + timedelta(seconds=122)))[0]
            async with admin.connect() as connection:
                statuses = (await connection.execute(text("SELECT id,status FROM routine_runs WHERE id IN (:first,:second,:third)"), {"first": first, "second": second, "third": third})).all()
                assert {row.id: row.status for row in statuses} == {first: "completed", second: "completed", third: "completed"}
                allowed = await connection.scalar(text("SELECT allowed_actions FROM bot_routines WHERE id=:id"), {"id": routine_id})
                assert "boundary:external_email:Send daily summary" in allowed
                count = await connection.scalar(text("SELECT count(*) FROM audit_logs WHERE tenant_id=:tenant AND action='approval.resolved'"), {"tenant": tenant_id})
                assert count == 2
            workflow_routine_id = uuid4()
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO bot_routines (id,tenant_id,workspace_id,bot_id,name,instruction_markdown,cron_expression,timezone,enabled,interval_seconds,workflow_id) VALUES (:id,:tenant,:workspace,:bot,'Workflow routine','# Review\nReview this summary.','* * * * *','UTC',true,60,:workflow)"), {
                    "id": workflow_routine_id, "tenant": tenant_id, "workspace": workspace_id,
                    "bot": bot_id, "workflow": workflow_id,
                })
            await runner.run_due(first_time + timedelta(seconds=183))
            async with admin.connect() as connection:
                workflow_run = (await connection.execute(text("SELECT id,workflow_run_id,status FROM routine_runs WHERE routine_id=:id"), {"id": workflow_routine_id})).one()
                assert workflow_run.status == "paused"
                assert workflow_run.workflow_run_id is not None
            routine_result = await coordinator.resume_from_approval(workflow_run.workflow_run_id, "allow_once")
            assert isinstance(routine_result, WorkflowState) and routine_result.status == "completed"
            async with admin.connect() as connection:
                assert await connection.scalar(text("SELECT status FROM routine_runs WHERE id=:id"), {"id": workflow_run.id}) == "completed"
            state = await runner.invoke_workflow(bot_id, workflow_id, "Review data")
            assert state.status == "paused"
            resumed = await coordinator.resume_from_approval(state.run_id, "allow_once")
            assert isinstance(resumed, WorkflowState)
            assert resumed.status == "completed"
            denied = await runner.invoke_workflow(bot_id, workflow_id, "Do not publish")
            assert denied.status == "paused"
            failed = await coordinator.resume_from_approval(denied.run_id, "deny")
            assert isinstance(failed, WorkflowState)
            assert failed.status == "failed"
            boundary_run_id = uuid4()
            boundary_state = WorkflowState(
                id=boundary_run_id, run_id=boundary_run_id, workflow_id=workflow_id,
                tenant_id=tenant_id, workspace_id=workspace_id, status="running",
                input_data={"task": "Review with external action"},
            )
            store = CheckpointStore(app, redis)
            await store.create_run(boundary_state)
            await store.save(boundary_state)
            guarded = ComputerSandboxSupervisor(
                app, DockerSandboxProvider(root), boundary_guard=coordinator.computer_guard,
            )
            guarded_access = ComputerAccess(tenant_id, workspace_id, run_id=boundary_run_id)
            guarded_computer = await guarded.create(guarded_access)
            await guarded.upload(guarded_access, guarded_computer.id, "victim.txt", b"remove me")

            async def discard_output(_stream: str, _content: str) -> None:
                return None

            with pytest.raises(PauseRequested):
                await guarded.execute_shell(guarded_access, guarded_computer.id, "rm victim.txt", 30, discard_output)
            assert (await store.load(tenant_id, workspace_id, boundary_run_id)).status == "paused"
            after_boundary = await coordinator.resume_from_approval(boundary_run_id, "allow_once")
            assert isinstance(after_boundary, WorkflowState)
            assert after_boundary.status == "paused"
            assert after_boundary.pending_boundary is None
            assert (await guarded.execute_shell(guarded_access, guarded_computer.id, "rm victim.txt", 30, discard_output)).exit_code == 0
            async with admin.connect() as connection:
                consumed = await connection.scalar(text("SELECT grant_consumed_at FROM approval_requests WHERE run_id=:run AND action='rm victim.txt'"), {"run": boundary_run_id})
                assert consumed is not None
            with pytest.raises(PermissionError):
                await guarded.execute_shell(guarded_access, guarded_computer.id, "rm victim.txt", 30, discard_output)
            final = await coordinator.resume_from_approval(boundary_run_id, "allow_once")
            assert isinstance(final, WorkflowState) and final.status == "completed"
            await guarded.terminate(guarded_access, guarded_computer.id)
            with pytest.raises(DBAPIError, match="immutable"):
                async with admin.begin() as connection:
                    await connection.execute(text("UPDATE audit_logs SET action='changed' WHERE tenant_id=:tenant"), {"tenant": tenant_id})
        finally:
            await redis.aclose()
            await app.dispose()
            await admin.dispose()
            scoped_root = root / str(tenant_id)
            if scoped_root.exists():
                rmtree(scoped_root)

    asyncio.run(check())
