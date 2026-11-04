from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from shutil import rmtree
from uuid import UUID, uuid4

import pytest
from autogen_core import FunctionCall
from autogen_core.models import CreateResult, ModelFamily, ModelInfo, RequestUsage
from autogen_ext.models.replay import ReplayChatCompletionClient
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nexusgen_bridge.sandbox_team import NexusGenCodeExecutionTool, NexusGenSandboxRunner
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.store import CheckpointStore
from crews.builder import CrewBuilder
from flows.compiler import FlowCompiler
from nexus_computer_sandbox import DockerSandboxSupervisor
from nexus_core_schema.models import CrewNodeSpec, RuntimeEvent, RuntimeEventType, WorkflowSpec


class ReviewResult(BaseModel):
    summary: str


def test_crew_builder_round_trips_jsonc_and_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-for-definition-only")
    builder = CrewBuilder({"ReviewResult": ReviewResult})
    spec = CrewNodeSpec.model_validate({
        "id": "review", "kind": "crew", "label": "Review",
        "agents": [{"id": "analyst", "role": "Analyst", "goal": "Analyze data", "model": "openai/gpt-4o-mini"}],
        "tasks": [{
            "id": "summary", "agent_id": "analyst", "description": "Summarize data",
            "expected_output": "A validated summary", "output_schema": "ReviewResult",
        }],
    })
    built = builder.build(spec)
    assert built.crew.tasks[0].output_pydantic is ReviewResult
    jsonc = tmp_path / "crew.jsonc"
    yaml_path = tmp_path / "crew.yaml"
    builder.export(spec, jsonc)
    builder.export(spec, yaml_path)
    assert builder.load(jsonc) == builder.load(yaml_path) == spec
    source = jsonc.read_text()
    jsonc.write_text("// reviewed config\n" + source.replace('"Review",', '"Review", // label\n'))
    assert builder.load(jsonc) == spec
    round_trip = builder.from_crew(built.crew, node_id="review", label="Review")
    assert round_trip.tasks[0].output_schema == "ReviewResult"


def test_event_bus_rejects_cross_scope_and_publishes_json() -> None:
    if "NEXUS_TEST_REDIS_URL" not in os.environ:
        pytest.skip("Redis test URL is not configured")

    async def check() -> None:
        redis = Redis.from_url(os.environ["NEXUS_TEST_REDIS_URL"], decode_responses=True)
        tenant_id, workspace_id, run_id = uuid4(), uuid4(), uuid4()
        emitter = RuntimeEventEmitter(redis, tenant_id, workspace_id, run_id)
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(emitter.channel)
            await pubsub.get_message(timeout=1)
            await emitter.emit(RuntimeEventType.FLOW_STATE_CHANGED, {"status": "running"})
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
            assert message is not None
            event = RuntimeEvent.model_validate_json(message["data"])
            assert (event.tenant_id, event.workspace_id, event.run_id) == (tenant_id, workspace_id, run_id)
            assert event.type == RuntimeEventType.FLOW_STATE_CHANGED
            with pytest.raises(ValueError, match="scope"):
                await RuntimeEventEmitter(redis, uuid4(), workspace_id, run_id).publish(event)
        finally:
            await pubsub.aclose()
            await redis.aclose()

    asyncio.run(check())


def test_hybrid_flow_executes_code_checkpoints_and_resumes() -> None:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL", "NEXUS_TEST_REDIS_URL", "NEXUS_SANDBOX_TEST_ROOT")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL, Redis, and a host-shared sandbox root are required")

    async def check() -> None:
        tenant_id, workspace_id, workflow_id, run_id, user_id = (uuid4() for _ in range(5))
        spec = WorkflowSpec.model_validate({
            "id": str(workflow_id), "tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
            "name": "Data review", "version": 1,
            "nodes": [
                {"id": "start", "kind": "start"},
                {
                    "id": "calculate", "kind": "sandbox", "label": "Calculate",
                    "coder_model": "coder-model", "reviewer_model": "reviewer-model",
                    "verification_command": "python -c \"assert open('result.txt').read().strip() == '6'\"",
                    "max_rounds": 2, "timeout_seconds": 60,
                },
                {
                    "id": "approve", "kind": "approval", "label": "Approve",
                    "action_description": "Publish calculated result", "required_role": "admin",
                },
                {
                    "id": "route", "kind": "router", "label": "Check result",
                    "routes": [{"name": "success", "field_path": "calculate.exit_code", "operator": "eq", "value": 0}],
                    "default_route": "failure",
                },
                {
                    "id": "unused", "kind": "approval", "label": "Failed result",
                    "action_description": "Review failed result", "required_role": "admin",
                },
            ],
            "edges": [
                {"source": "start", "target": "calculate"},
                {"source": "calculate", "target": "route"},
                {"source": "route", "target": "approve", "route": "success"},
                {"source": "route", "target": "unused", "route": "failure"},
            ],
        })
        admin_engine = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"])
        app_engine = create_async_engine(os.environ["NEXUS_TEST_APP_DATABASE_URL"])
        redis = Redis.from_url(os.environ["NEXUS_TEST_REDIS_URL"], decode_responses=True)
        root = Path(os.environ["NEXUS_SANDBOX_TEST_ROOT"])
        root.mkdir(parents=True, exist_ok=True)
        try:
            async with admin_engine.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Test')"), {"id": tenant_id})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :tenant, 'Test')"), {"id": workspace_id, "tenant": tenant_id})
                await connection.execute(text("INSERT INTO workflows (id, tenant_id, workspace_id, name, version, spec) VALUES (:id, :tenant, :workspace, 'Data review', 1, CAST(:spec AS jsonb))"), {
                    "id": workflow_id, "tenant": tenant_id, "workspace": workspace_id,
                    "spec": spec.model_dump_json(),
                })
                await connection.execute(text("INSERT INTO users (id, tenant_id, workspace_id, email, password_hash, display_name) VALUES (:id, :tenant, :workspace, 'reviewer@example.invalid', 'test', 'Reviewer')"), {"id": user_id, "tenant": tenant_id, "workspace": workspace_id})
                await connection.execute(text("INSERT INTO workspace_members (id, tenant_id, workspace_id, user_id, role) VALUES (:id, :tenant, :workspace, :user, 'admin')"), {"id": uuid4(), "tenant": tenant_id, "workspace": workspace_id, "user": user_id})

            code = "numbers = [1, 2, 3]\nresult = sum(numbers)\nopen('result.txt', 'w').write(str(result))\nprint(result)\n"
            model_info: ModelInfo = {
                "vision": False, "function_calling": True, "json_output": False,
                "family": ModelFamily.UNKNOWN, "structured_output": False,
            }

            def client_factory(model: str) -> ReplayChatCompletionClient:
                if model == "coder-model":
                    response = CreateResult(
                        finish_reason="function_calls",
                        content=[FunctionCall(id="execute-1", name="execute_python", arguments=json.dumps({"code": code}))],
                        usage=RequestUsage(prompt_tokens=12, completion_tokens=8),
                        cached=False,
                    )
                    return ReplayChatCompletionClient([response], model_info=model_info)
                return ReplayChatCompletionClient(["APPROVED. The sum is 6."])

            emitter = RuntimeEventEmitter(redis, tenant_id, workspace_id, run_id)
            checkpoints = CheckpointStore(app_engine, redis)
            runner = NexusGenSandboxRunner(DockerSandboxSupervisor(root), client_factory)
            tool_spec = next(node for node in spec.nodes if node.id == "calculate")
            assert tool_spec.kind == "sandbox"
            tool = NexusGenCodeExecutionTool(
                runner, tool_spec, RuntimeEventEmitter(redis, tenant_id, workspace_id, uuid4())
            )
            assert tool.name == "nexus_code_execution"
            compiled = FlowCompiler(checkpoints, emitter, runner).compile(
                spec, run_id, {"task": "Sum the numbers 1, 2, and 3 and save the result"}
            )
            pubsub = redis.pubsub()
            await pubsub.subscribe(emitter.channel)
            await pubsub.get_message(timeout=1)
            try:
                paused = await compiled.run()
                assert paused.status == "paused"
                assert paused.pending_approval_id is not None
                assert paused.node_outputs["calculate"]["exit_code"] == 0
                assert "result.txt" in paused.node_outputs["calculate"]["artifacts"]
                assert paused.node_outputs["calculate"]["metrics"]["attempts"] == 1
                assert paused.node_outputs["route"]["route"] == "success"
                assert "unused" not in paused.node_outputs
                saved = await checkpoints.load(tenant_id, workspace_id, run_id)
                assert saved.sequence == paused.sequence
                await checkpoints.resolve_approval(tenant_id, workspace_id, paused.pending_approval_id, user_id, "allowed_once")
                completed = await compiled.resume()
                assert completed.status == "completed"
                assert completed.node_outputs["approve"]["decision"] == "allowed_once"
                assert completed.node_outputs["calculate"]["metrics"]["attempts"] == 1
                assert "unused" not in completed.node_outputs
                assert completed.sequence > paused.sequence
                async with admin_engine.connect() as connection:
                    count = await connection.scalar(text("SELECT count(*) FROM run_checkpoints WHERE run_id = :run"), {"run": run_id})
                    assert count is not None and count >= 5
                events: list[str] = []
                while message := await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2):
                    events.append(RuntimeEvent.model_validate_json(message["data"]).type)
                assert RuntimeEventType.NEXUSGEN_CODE_GENERATED in events
                assert RuntimeEventType.SANDBOX_TERMINAL_OUTPUT in events
                assert RuntimeEventType.APPROVAL_REQUIRED in events
                assert RuntimeEventType.RUN_COMPLETED in events
                delegated = json.loads(await tool._arun("Sum the numbers and save the result"))
                assert delegated["exit_code"] == 0, delegated
                assert "result.txt" in delegated["artifacts"]
            finally:
                await pubsub.aclose()
        finally:
            await redis.aclose()
            await app_engine.dispose()
            await admin_engine.dispose()
            scoped_root = root / str(tenant_id)
            if scoped_root.exists():
                rmtree(scoped_root)

    asyncio.run(check())
