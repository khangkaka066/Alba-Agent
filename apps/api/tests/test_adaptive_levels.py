from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from architect.adaptive import assess
from architect.team_generator import ArchitectWorkspaceContext, MetaArchitectService
from flows.compiler import FlowCompiler
from nexus_core_schema.models import NexusGenSandboxNodeSpec, RouterNodeSpec, WorkflowSpec
from nexusgen_bridge.sandbox_team import SandboxResult

TENANT, WORKSPACE = uuid4(), uuid4()
MODELS = ("openai/gpt-4.1-mini", "openai/gpt-4.1", "anthropic/claude-sonnet-4")


def _context() -> ArchitectWorkspaceContext:
    return ArchitectWorkspaceContext(tenant_id=TENANT, workspace_id=WORKSPACE, available_models=MODELS)


def _generator(seen: list[str]) -> Any:
    async def generate(prompt: str, output_model: type[BaseModel]) -> Any:
        seen.append(output_model.__name__)
        if output_model.__name__ == "_StudioDraft":
            return {"name": "Studio", "summary": "A studio that ships a small game.", "direction": "Short.", "objectives": {}, "design_reasoning": []}
        return {"name": "Quick flow", "summary": "One crew does the work.",
                "stages": [{"kind": "crew", "label": "Work", "purpose": "Do the work thoroughly."}]}

    return generate


@pytest.mark.parametrize(("prompt", "files", "level"), [
    ("`python -m unittest test_ledger` fails; fix the ledger package", (), "solo"),
    ("Implement a token bucket rate limiter in Python", (), "solo"),
    ("Tính toán lãi suất kép bằng python", (), "solo"),
    ("Summarise what these figures mean", ("accounts.py",), "solo"),
    ("Generate a promotional video for our launch", (), "team"),
    ("Fix the parser and then email the result to the customer", (), "team"),
    ("Plan a quarterly marketing campaign", (), "team"),
    ("Write a short essay about autumn", (), "team"),
])
def test_assessment_sends_only_plain_code_requests_down_the_light_path(prompt: str, files: tuple[str, ...], level: str) -> None:
    result = assess(prompt, files)
    assert result.level == level and result.reason


def test_auto_builds_the_light_path_without_asking_the_architect_model() -> None:
    seen: list[str] = []
    service = MetaArchitectService(_generator(seen), FlowCompiler.validate)
    spec, summary = asyncio.run(service.generate_workflow("Fix the failing unit tests in this Python package", _context(), rigor="auto"))
    assert seen == [], "the light path must not spend a model call on planning"
    assert summary["level"] == "solo" and summary["agent_count"] == 2 and summary["level_reason"]
    nodes = {node.id: node for node in spec.nodes}
    assert [node.kind for node in spec.nodes] == ["start", "sandbox", "router", "sandbox"]
    solo, repair, gate = nodes["solo"], nodes["repair"], nodes["gate"]
    assert isinstance(solo, NexusGenSandboxNodeSpec) and isinstance(repair, NexusGenSandboxNodeSpec) and isinstance(gate, RouterNodeSpec)
    assert solo.on_failure == "continue" and repair.on_failure == "fail"
    assert solo.coder_model == "openai/gpt-4.1-mini" and repair.coder_model == "openai/gpt-4.1", "repair runs on the stronger model"
    assert {(edge.source, edge.target, edge.route) for edge in spec.edges} == {("start", "solo", None), ("solo", "gate", None), ("gate", "repair", "escalate")}


def test_a_preferred_model_is_used_for_the_first_attempt() -> None:
    service = MetaArchitectService(_generator([]), FlowCompiler.validate)
    spec, _ = asyncio.run(service.generate_workflow("Fix this python bug", _context(), rigor="solo", preferred_model="anthropic/claude-sonnet-4"))
    solo = next(node for node in spec.nodes if node.id == "solo")
    assert isinstance(solo, NexusGenSandboxNodeSpec) and solo.coder_model == "anthropic/claude-sonnet-4"


def test_auto_keeps_a_planned_team_studios_and_explicit_minimal() -> None:
    seen: list[str] = []
    service = MetaArchitectService(_generator(seen), FlowCompiler.validate)
    team, summary = asyncio.run(service.generate_workflow("Plan a quarterly marketing campaign", _context(), rigor="auto"))
    assert seen == ["_WorkflowDraft"] and summary["level"] == "team" and team.modes.rigor == "minimal"
    assert all(node.kind != "router" for node in team.nodes)
    seen.clear()
    _, studio_summary = asyncio.run(service.generate_workflow("Build a roguelike game with pixel art", _context(), rigor="auto"))
    assert seen == ["_StudioDraft"] and studio_summary["rigor"] == "full_studio"
    seen.clear()
    asyncio.run(service.generate_workflow("Fix this python bug", _context(), rigor="minimal"))
    assert seen == ["_WorkflowDraft"], "an explicit minimal request still plans a team"
    seen.clear()
    asyncio.run(service.generate_workflow("Fix this python bug", _context()))
    assert seen == ["_WorkflowDraft"], "callers that pass no rigor keep the previous behaviour"


class _Checkpoints:
    async def create_run(self, state: Any) -> None: ...
    async def save(self, state: Any) -> None: ...
    async def record_failure(self, state: Any, failure: dict[str, Any]) -> None: ...


class _Emitter:
    def __init__(self, run_id: UUID) -> None:
        self.tenant_id, self.workspace_id, self.run_id = TENANT, WORKSPACE, run_id

    async def emit(self, kind: Any, payload: dict[str, Any], node_id: str | None = None) -> None: ...


class _Runner:
    """Answers each sandbox node from a script and remembers the task text it was given."""

    def __init__(self, script: dict[str, SandboxResult]) -> None:
        self.script = script
        self.tasks: dict[str, str] = {}

    async def run(self, task: str, node: NexusGenSandboxNodeSpec, emitter: Any, input_files: dict[str, bytes] | None = None) -> SandboxResult:
        self.tasks[node.id] = task
        return self.script[node.id]


def _spec() -> WorkflowSpec:
    service = MetaArchitectService(_generator([]), FlowCompiler.validate)
    spec, _ = asyncio.run(service.generate_workflow("Fix this python bug", _context(), rigor="solo"))
    return spec


def _execute(runner: _Runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    compiler = FlowCompiler(cast(Any, _Checkpoints()), cast(Any, _Emitter(run_id)), cast(Any, runner))
    return asyncio.run(compiler.compile(_spec(), run_id, {"task": "Fix this python bug"}).run())


VERIFIED = SandboxResult(summary="all fixed", artifacts=("a.py",), exit_code=0, metrics={"attempts": 1}, verification={"status": "verified"})
FAILED = SandboxResult(summary="gave up", artifacts=("a.py",), exit_code=1, metrics={"attempts": 4},
                       verification={"status": "failed", "reason": "2 of 5 tests failed"})


def test_a_verified_first_attempt_ends_the_run_and_never_calls_the_repair_team(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _Runner({"solo": VERIFIED})
    state = _execute(runner, tmp_path, monkeypatch)
    assert state.status == "completed" and list(runner.tasks) == ["solo"]
    assert state.node_outputs["solo"]["verified"] is True
    assert state.node_outputs["gate"]["route"] == "verified"
    assert state.unverified_nodes == []


def test_a_failed_first_attempt_runs_one_repair_that_sees_the_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _Runner({"solo": FAILED, "repair": VERIFIED})
    state = _execute(runner, tmp_path, monkeypatch)
    assert state.status == "completed" and list(runner.tasks) == ["solo", "repair"]
    assert state.node_outputs["solo"]["verified"] is False and state.node_outputs["gate"]["route"] == "escalate"
    seen_by_repair = json.loads(runner.tasks["repair"])["completed_node_outputs"]["solo"]
    assert seen_by_repair["failure_reason"] == "2 of 5 tests failed" and seen_by_repair["summary"] == "gave up"
    assert state.unverified_nodes == [], "the failed first attempt must not be delivered as an unverified result"


def test_the_run_fails_when_the_repair_attempt_does_not_verify_either(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _Runner({"solo": FAILED, "repair": FAILED})
    with pytest.raises(RuntimeError, match="2 of 5 tests failed"):
        _execute(runner, tmp_path, monkeypatch)
    assert list(runner.tasks) == ["solo", "repair"]


def test_a_node_that_does_not_continue_still_fails_the_run_at_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec()
    strict = spec.model_copy(update={"nodes": tuple(
        node.model_copy(update={"on_failure": "fail"}) if node.id == "solo" else node for node in spec.nodes)})
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    runner = _Runner({"solo": FAILED, "repair": VERIFIED})
    compiler = FlowCompiler(cast(Any, _Checkpoints()), cast(Any, _Emitter(run_id)), cast(Any, runner))
    with pytest.raises(RuntimeError, match="Sandbox verification failed"):
        asyncio.run(compiler.compile(strict, run_id, {"task": "x"}).run())
    assert list(runner.tasks) == ["solo"]
