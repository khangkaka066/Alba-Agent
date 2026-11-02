"""Phase 17: hierarchical studio graphs, artifact-contract hooks and the quality-gate rework loop."""

from __future__ import annotations

import asyncio
import json
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from architect.team_generator import ArchitectWorkspaceContext, MetaArchitectService
from crews.builder import CrewBuilder, _task_description
from flows.compiler import FlowCompiler, json_safe
from hooks import LifecycleHookEngine, PathScopedRuleInjector
from nexus_core_schema.artifacts import artifact_directory, artifact_file, list_artifacts
from nexus_core_schema.models import (
    AgentSpec,
    CrewNodeSpec,
    TaskSpec,
    WorkflowSpec,
)
from nexus_core_schema_templates.studios import STUDIO_BLUEPRINTS, STUDIO_BY_ID, build_studio_graph, detect_studio

MODEL = "openai/gpt-4.1-mini"
TENANT, WORKSPACE = uuid4(), uuid4()


def _png(path: Path, width: int = 8, height: int = 8) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + bytes([200, 40, 40]) * width for _ in range(height))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    )


def _agent(identifier: str, tier: str = "specialist", tools: tuple[str, ...] = ()) -> AgentSpec:
    return AgentSpec(id=identifier, role=identifier, goal="goal", model=MODEL, tier=tier, tool_ids=tools)  # type: ignore[arg-type]


def _task(identifier: str, agent: str, paths: tuple[str, ...] = ()) -> TaskSpec:
    return TaskSpec(id=identifier, agent_id=agent, description="d", expected_output="e", output_schema="S",
                    output_schema_json={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
                    expected_artifact_paths=paths)


# --- schema -----------------------------------------------------------------------------------------------------

def test_managed_crew_requires_hierarchical_lead_without_tools_or_tasks() -> None:
    lead, worker = _agent("lead", "lead"), _agent("worker")
    ok = CrewNodeSpec(id="dept", label="Dept", agents=(lead, worker), tasks=(_task("t", "worker"),), process="hierarchical", manager_agent_id="lead")
    assert ok.manager_agent_id == "lead"
    with pytest.raises(ValidationError, match="hierarchical"):
        CrewNodeSpec(id="dept", label="Dept", agents=(lead, worker), tasks=(_task("t", "worker"),), manager_agent_id="lead")
    with pytest.raises(ValidationError, match="cannot hold tools"):
        CrewNodeSpec(id="dept", label="Dept", agents=(_agent("lead", "lead", ("web_search",)), worker), tasks=(_task("t", "worker"),),
                     process="hierarchical", manager_agent_id="lead")
    with pytest.raises(ValidationError, match="not the crew manager"):
        CrewNodeSpec(id="dept", label="Dept", agents=(lead, worker), tasks=(_task("t", "lead"),), process="hierarchical", manager_agent_id="lead")


@pytest.mark.parametrize("path", ["../escape.md", "a/../b.md", "/abs.md", ".hidden/x.md", "a//b.md", "x" * 90 + ".md"])
def test_unsafe_artifact_paths_are_rejected_by_the_contract(path: str) -> None:
    with pytest.raises(ValidationError):
        _task("t", "worker", (path,))


def _workflow(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> WorkflowSpec:
    return WorkflowSpec.model_validate({
        "id": str(uuid4()), "tenant_id": str(TENANT), "workspace_id": str(WORKSPACE), "name": "Loop", "version": 1,
        "nodes": nodes, "edges": edges,
    })


def _crew_node(identifier: str) -> dict[str, Any]:
    return {"id": identifier, "kind": "crew", "label": identifier, "agents": [_agent("a" + identifier).model_dump(mode="json")],
            "tasks": [_task("t" + identifier, "a" + identifier).model_dump(mode="json")]}


def test_cycles_are_only_valid_through_router_loop_back_edges() -> None:
    router = {"id": "gate", "kind": "router", "label": "Gate", "routes": [{"name": "again", "field_path": "x", "operator": "exists"}],
              "default_route": "done", "max_loop_iterations": 2}
    nodes = [{"id": "start", "kind": "start"}, _crew_node("work"), router]
    base = [{"source": "start", "target": "work"}, {"source": "work", "target": "gate"}]
    valid = _workflow(nodes, [*base, {"source": "gate", "target": "work", "route": "again", "loop_back": True}])
    assert FlowCompiler.validate(valid) is valid
    with pytest.raises(ValidationError, match="loop budget"):
        _workflow([{**router, "max_loop_iterations": 0}, *nodes[:2]], [*base, {"source": "gate", "target": "work", "route": "again", "loop_back": True}])
    with pytest.raises(ValidationError, match="must leave a router"):
        _workflow(nodes, [*base, {"source": "work", "target": "gate", "loop_back": True}])
    plain_cycle = _workflow(nodes, [*base, {"source": "gate", "target": "work", "route": "again"}])
    with pytest.raises(ValueError, match="cycles"):
        FlowCompiler.validate(plain_cycle)


# --- hooks ------------------------------------------------------------------------------------------------------

def test_artifact_contract_verifies_recovers_documents_and_flags_missing_code_and_fake_media(tmp_path: Path) -> None:
    engine = LifecycleHookEngine()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("print(1)\n")
    (tmp_path / "src" / "empty.py").write_text("")
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "fake.png").write_bytes(b"not a png at all")
    _png(tmp_path / "media" / "real.png")
    report = engine.after_node(
        tmp_path, "dept",
        ("src/ok.py", "src/empty.py", "src/missing.py", "media/fake.png", "media/real.png", "design/gdd.md", "data/facts.json"),
        {"summary": "Vision statement", "content": "Long form text"},
    )
    by_path = {check.path: check for check in report.checks}
    assert by_path["src/ok.py"].status == "verified"
    assert by_path["src/empty.py"].status == "invalid"
    assert by_path["src/missing.py"].status == "missing"
    assert by_path["media/fake.png"].status == "invalid"
    assert by_path["media/real.png"].status == "verified"
    assert by_path["design/gdd.md"].status == "recovered"
    assert "Vision statement" in (tmp_path / "design" / "gdd.md").read_text()
    assert json.loads((tmp_path / "data" / "facts.json").read_text())["summary"] == "Vision statement"
    assert not report.passed
    output = report.as_output()
    assert output["recovered"] == ["design/gdd.md", "data/facts.json"]
    assert sorted(output["missing"]) == ["src/missing.py"]
    assert len(output["warnings"]) == 5


def test_artifact_contract_never_synthesises_source_code_or_escapes_the_run_directory(tmp_path: Path) -> None:
    report = LifecycleHookEngine().after_node(tmp_path, "dept", ("src/main.py", "../outside.md"), {"summary": "text"})
    assert [check.status for check in report.checks] == ["missing", "invalid"]
    assert not (tmp_path / "src").exists() and not (tmp_path.parent / "outside.md").exists()


def test_sandbox_exports_are_materialised_before_validation(tmp_path: Path) -> None:
    report = LifecycleHookEngine().after_node(tmp_path, "build", ("src/game.py",), None, {"src/game.py": b"print('play')\n"})
    assert report.passed and (tmp_path / "src" / "game.py").read_text() == "print('play')\n"


def test_path_scoped_rules_follow_declared_paths() -> None:
    injector = PathScopedRuleInjector()
    block = injector.instruction_block(["src/gameplay/rules.py", "design/gdd.md"])
    assert "src/gameplay/rules.py" in block and "fixed-timestep" in block and "acceptance criteria" in block
    assert "media" not in injector.instruction_block(["tests/test_a.py"]).split("standards:")[1]
    assert injector.instruction_block([]) == ""


def test_visual_evidence_requires_a_real_rendered_frame(tmp_path: Path) -> None:
    engine = LifecycleHookEngine()
    assert not engine.visual.check(tmp_path).passed
    (tmp_path / "qa" / "evidence").mkdir(parents=True)
    (tmp_path / "qa" / "evidence" / "shot.png").write_bytes(b"placeholder")
    assert not engine.visual.check(tmp_path).passed
    _png(tmp_path / "qa" / "evidence" / "shot.png")
    report = engine.visual.check(tmp_path)
    assert report.passed and report.files == ("qa/evidence/shot.png",)


def test_gate_names_the_earliest_responsible_department(tmp_path: Path) -> None:
    engine = LifecycleHookEngine()
    outputs = {
        "design": {"artifact_contract": {"passed": True}},
        "engineering": {"artifact_contract": {"passed": False, "missing": ["src/main.py"], "invalid": []}},
        "qa": {"gate_passed": False, "failing_department": "design"},
    }
    verdict = engine.evaluate_gate(tmp_path, outputs, {}, ["design", "engineering", "qa"], ["design", "engineering"], False)
    assert not verdict.gate_passed and verdict.failing_department == "design" and verdict.missing == ["src/main.py"]
    clean = engine.evaluate_gate(tmp_path, {"design": {"artifact_contract": {"passed": True}}}, {}, ["design"], ["design"], False)
    assert clean.gate_passed and clean.failing_department is None
    needs_evidence = engine.evaluate_gate(tmp_path, {}, {"build": ("qa/evidence/p.png",)}, ["build"], ["build"], True)
    assert not needs_evidence.gate_passed and needs_evidence.failing_department == "build"


# --- nested artifact paths ---------------------------------------------------------------------------------------

def test_artifact_files_support_safe_nested_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run = uuid4()
    directory = artifact_directory(TENANT, WORKSPACE, run)
    (directory / "design").mkdir(parents=True)
    (directory / "design" / "gdd.md").write_text("# GDD")
    (directory / ".secret").write_text("x")
    listed = list_artifacts(TENANT, WORKSPACE, run, {"design": {"artifact_contract": {"verified": ["design/gdd.md"], "recovered": []}}})
    assert [item["filename"] for item in listed] == ["design/gdd.md"]
    assert listed[0]["created_by_node"] == "design" and listed[0]["download_url"].endswith("/artifacts/design/gdd.md")
    assert artifact_file(directory, "design/gdd.md").is_file()
    for bad in ("../x", "design/../../x", "/etc/passwd", ".secret", "a\\b", "design//gdd.md", ""):
        with pytest.raises(ValueError):
            artifact_file(directory, bad)
    (directory / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        artifact_file(directory, "link/anything.md")


# --- studios ----------------------------------------------------------------------------------------------------

def _spec(graph: Any, name: str = "Studio") -> WorkflowSpec:
    return WorkflowSpec(id=uuid4(), tenant_id=TENANT, workspace_id=WORKSPACE, name=name, version=1,
                        nodes=tuple(graph.nodes), edges=tuple(graph.edges), layout=graph.layout, modes=graph.modes)


@pytest.mark.parametrize(("blueprint_id", "agents"), [("full-game-development-studio", 49), ("cinematic-video-documentary-studio", 26), ("feature-film-production-studio", 50), ("full-stack-software-factory", 32)])
def test_full_studio_blueprints_have_the_advertised_agent_counts_and_three_tiers(blueprint_id: str, agents: int) -> None:
    graph = build_studio_graph(STUDIO_BY_ID[blueprint_id], "full_studio", model=MODEL, director_model="openai/gpt-4.1")
    spec = FlowCompiler.validate(_spec(graph))
    assert graph.agent_count == agents
    assert 10 <= len(spec.nodes) <= 16
    crews = [node for node in spec.nodes if isinstance(node, CrewNodeSpec)]
    tiers = {agent.tier for crew in crews for agent in crew.agents}
    assert tiers == {"director", "lead", "specialist"}
    for crew in crews:
        if crew.id == "direction":
            assert {agent.tier for agent in crew.agents} == {"director"} and crew.process == "sequential"
            continue
        lead = next(agent for agent in crew.agents if agent.id == crew.manager_agent_id)
        assert crew.process == "hierarchical" and lead.tier == "lead" and not lead.tool_ids
        assert all(agent.tier == "specialist" for agent in crew.agents if agent.id != lead.id)
        assert all(task.expected_artifact_paths for task in crew.tasks)
    assert set(spec.layout) == {node.id for node in spec.nodes}
    assert len({(round(p.x), round(p.y)) for p in spec.layout.values()}) == len(spec.nodes)


def test_wave_one_departments_run_in_parallel_and_the_quality_gate_loops_back_to_each_team() -> None:
    blueprint = STUDIO_BY_ID["full-game-development-studio"]
    spec = _spec(build_studio_graph(blueprint, "full_studio", model=MODEL, director_model=MODEL))
    forward = [edge for edge in spec.edges if not edge.loop_back]
    wave_one = [dept.key for dept in blueprint.wave_one]
    assert {edge.target for edge in forward if edge.source == "direction"} == set(wave_one)
    assert {edge.source for edge in forward if edge.target == "engineering"} == set(wave_one)
    assert {edge.source for edge in forward if edge.target == "qa"} == {"engineering", "build"}
    assert all(layout_x < spec.layout["engineering"].x for layout_x in (spec.layout[key].x for key in wave_one))
    loops = {edge.target for edge in spec.edges if edge.loop_back}
    assert loops == {*wave_one, "engineering", "build", "direction"}
    gate = next(node for node in spec.nodes if node.id == "quality_gate")
    assert gate.kind == "router" and gate.artifact_gate and gate.max_loop_iterations == 2
    sign_off_index = [node.id for node in spec.nodes].index("sign_off")
    assert [node.kind for node in spec.nodes][sign_off_index] == "approval"
    assert {edge.source for edge in forward if edge.target == "sign_off"} == {"quality_gate"}
    assert spec.modes.rigor == "full_studio" and spec.modes.path_rules


@pytest.mark.parametrize("blueprint", STUDIO_BLUEPRINTS, ids=lambda item: item.domain)
def test_standard_rigor_is_a_nine_node_studio_with_twelve_to_twenty_agents(blueprint: Any) -> None:
    graph = build_studio_graph(blueprint, "standard", model=MODEL, director_model=MODEL)
    spec = FlowCompiler.validate(_spec(graph))
    assert 7 <= len(spec.nodes) <= 9 and 12 <= graph.agent_count <= 20
    assert spec.modes.rigor == "standard"


def test_studio_detection_distinguishes_domains_and_ignores_small_requests() -> None:
    assert detect_studio("Build a roguelike game with pixel art").domain == "game"  # type: ignore[union-attr]
    assert detect_studio("Create a documentary video campaign for the museum").domain == "video"  # type: ignore[union-attr]
    assert detect_studio("Tạo ứng dụng SaaS quản lý khách hàng").domain == "software"  # type: ignore[union-attr]
    assert detect_studio("Summarise this CSV") is None
    assert detect_studio("game design ideas") is None


def test_agent_ids_are_unique_across_the_whole_studio() -> None:
    for blueprint in STUDIO_BLUEPRINTS:
        spec = _spec(build_studio_graph(blueprint, "full_studio", model=MODEL, director_model=MODEL))
        ids = [agent.id for node in spec.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents]
        assert len(ids) == len(set(ids))


# --- crew builder -----------------------------------------------------------------------------------------------

def test_task_descriptions_always_receive_the_request_and_upstream_results() -> None:
    plain = _task_description("Write the brief")
    assert "{input}" in plain and "{nodes}" in plain
    assert _task_description("Use {input} and {nodes}").count("{input}") == 1
    assert "{unknown}" not in _task_description("Cite {unknown}") and "(unknown)" in _task_description("Cite {unknown}")


def test_hierarchical_crew_uses_the_department_lead_as_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    blueprint = STUDIO_BY_ID["full-stack-software-factory"]
    spec = _spec(build_studio_graph(blueprint, "standard", model=MODEL, director_model=MODEL, tools=set()))
    backend = next(node for node in spec.nodes if isinstance(node, CrewNodeSpec) and node.id == "backend")
    built = CrewBuilder({"S": BaseModel}).build(backend, None, {backend.tasks[0].id: "Required deliverables"})
    manager = built.crew.manager_agent
    assert manager is not None and manager.role == "Backend Lead" and manager.allow_delegation
    assert manager not in built.crew.agents and len(built.crew.agents) == len(backend.agents) - 1
    assert "Required deliverables" in built.crew.tasks[0].description and "{input}" in built.crew.tasks[0].description


def test_json_safe_converts_runtime_values_for_crew_inputs() -> None:
    value = json_safe({"artifacts": ("a.md", "b.md"), "id": UUID(int=1), "nested": {"t": (1, 2)}})
    assert value == {"artifacts": ["a.md", "b.md"], "id": str(UUID(int=1)), "nested": {"t": [1, 2]}}


# --- architect --------------------------------------------------------------------------------------------------

def _context() -> ArchitectWorkspaceContext:
    return ArchitectWorkspaceContext(
        tenant_id=TENANT, workspace_id=WORKSPACE, available_models=(MODEL, "openai/gpt-4.1", "anthropic/claude-sonnet-4"),
        builtin_tool_ids=("report_exporter", "web_search", "media_generation"),
    )


def _studio_generator(seen: list[str]) -> Callable[[str, type[BaseModel]], Any]:
    async def generate(prompt: str, output_model: type[BaseModel]) -> Any:
        seen.append(output_model.__name__)
        if output_model.__name__ == "_StudioDraft":
            return {"name": "Pixel quest studio", "summary": "A studio that ships a small pixel game.", "direction": "Cosy, readable, short sessions.",
                    "objectives": {"design": "Three-room dungeon loop", "not_a_department": "ignored"}, "design_reasoning": ["Parallel departments"]}
        return {"name": "Quick flow", "summary": "One crew does the work.",
                "stages": [{"kind": "crew", "label": "Work", "purpose": "Do the work thoroughly."}]}

    return generate


def test_meta_architect_builds_a_full_studio_for_product_requests_and_keeps_small_requests_minimal() -> None:
    seen: list[str] = []
    service = MetaArchitectService(_studio_generator(seen), FlowCompiler.validate)
    spec, summary = asyncio.run(service.generate_workflow("Build a roguelike game with pixel art", _context()))
    assert seen == ["_StudioDraft"] and summary["rigor"] == "full_studio" and summary["agent_count"] == 49
    assert summary["studio"] == "full-game-development-studio" and len(summary["agents"]) == 49
    assert spec.modes.rigor == "full_studio" and spec.name == "Pixel quest studio"
    design = next(node for node in spec.nodes if node.id == "design")
    assert isinstance(design, CrewNodeSpec) and "Three-room dungeon loop" in design.tasks[0].description
    assert all(tool in {"report_exporter", "web_search", "media_generation"} for node in spec.nodes if isinstance(node, CrewNodeSpec)
               for agent in node.agents for tool in agent.tool_ids)
    direction = next(node for node in spec.nodes if node.id == "direction")
    assert isinstance(direction, CrewNodeSpec) and all(agent.model == "openai/gpt-4.1" for agent in direction.agents)

    seen.clear()
    small, small_summary = asyncio.run(service.generate_workflow("Summarise this CSV file", _context()))
    assert seen == ["_WorkflowDraft"] and small.modes.rigor == "minimal" and "rigor" not in small_summary


def test_explicit_rigor_overrides_detection() -> None:
    seen: list[str] = []
    service = MetaArchitectService(_studio_generator(seen), FlowCompiler.validate)
    quick, _ = asyncio.run(service.generate_workflow("Build a roguelike game", _context(), rigor="minimal"))
    assert seen == ["_WorkflowDraft"] and quick.modes.rigor == "minimal"
    standard, summary = asyncio.run(service.generate_workflow("Build a roguelike game", _context(), rigor="standard"))
    assert standard.modes.rigor == "standard" and 12 <= summary["agent_count"] <= 20 and len(standard.nodes) <= 9
    report, report_summary = asyncio.run(service.generate_workflow("Compare vendors", _context(), rigor="standard"))
    assert report.modes.rigor == "standard" and report_summary["studio"] == "full-stack-software-factory"


# --- runtime: quality gate rework loop --------------------------------------------------------------------------

class _MemoryCheckpoints:
    def __init__(self) -> None:
        self.saved: list[int] = []
        self.failure: dict[str, Any] | None = None

    async def create_run(self, state: Any) -> None:
        self.saved.append(state.sequence)

    async def save(self, state: Any) -> None:
        self.saved.append(state.sequence)

    async def record_failure(self, state: Any, failure: dict[str, Any]) -> None:
        self.failure = failure


class _Emitter:
    def __init__(self, run_id: UUID) -> None:
        self.tenant_id, self.workspace_id, self.run_id = TENANT, WORKSPACE, run_id
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit(self, kind: Any, payload: dict[str, Any], node_id: str | None = None) -> None:
        self.events.append((str(getattr(kind, "value", kind)), payload))


class _Result(BaseModel):
    summary: str = "done"
    content: str = "text"
    files_written: list[str] = []
    gate_passed: bool = True
    failing_department: str = ""


class _FakeCrewBuilder:
    """Stands in for model-backed crews: each node writes its files according to a per-node behaviour."""

    def __init__(self, directory: Path, behaviours: dict[str, Callable[[int], dict[str, Any]]]) -> None:
        self.directory, self.behaviours = directory, behaviours
        self.calls: dict[str, int] = {}
        self.inputs: list[dict[str, Any]] = []
        self.preambles: dict[str, dict[str, str]] = {}

    def build(self, node: CrewNodeSpec, _overrides: Any = None, preambles: dict[str, str] | None = None) -> Any:
        self.preambles[node.id] = dict(preambles or {})
        builder = self

        class Crew:
            async def kickoff_async(self, inputs: dict[str, Any]) -> Any:
                builder.inputs.append(inputs)
                builder.calls[node.id] = builder.calls.get(node.id, 0) + 1
                result = builder.behaviours[node.id](builder.calls[node.id])
                for relative, content in result.get("files", {}).items():
                    target = builder.directory / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
                return SimpleNamespace(pydantic=_Result(**result.get("fields", {})), tasks_output=[], token_usage=None)

        return SimpleNamespace(crew=Crew())


def _gate_workflow() -> WorkflowSpec:
    def crew(identifier: str, paths: tuple[str, ...] = ()) -> dict[str, Any]:
        node = _crew_node(identifier)
        node["expected_artifact_paths"] = list(paths)
        return node

    gate = {
        "id": "gate", "kind": "router", "label": "Gate", "artifact_gate": True, "max_loop_iterations": 2, "default_route": "escalate",
        "routes": [{"name": "pass", "field_path": "gate__gate.gate_passed", "operator": "eq", "value": True},
                   {"name": "rework_build", "field_path": "gate__gate.failing_department", "operator": "eq", "value": "build"}],
    }
    return _workflow(
        [{"id": "start", "kind": "start"}, crew("build", ("src/main.py",)), crew("qa"), gate, crew("release")],
        [{"source": "start", "target": "build"}, {"source": "build", "target": "qa"}, {"source": "qa", "target": "gate"},
         {"source": "gate", "target": "release", "route": "pass"},
         {"source": "gate", "target": "build", "route": "rework_build", "loop_back": True}],
    )


def _run(spec: WorkflowSpec, builder: _FakeCrewBuilder, run_id: UUID) -> tuple[Any, _Emitter]:
    emitter = _Emitter(run_id)
    compiler = FlowCompiler(cast(Any, _MemoryCheckpoints()), cast(Any, emitter), cast(Any, None), cast(Any, builder))
    state = asyncio.run(compiler.compile(spec, run_id, {"task": "Make it"}).run())
    return state, emitter


def test_quality_gate_sends_missing_artifacts_back_to_the_responsible_department(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    directory = artifact_directory(TENANT, WORKSPACE, run_id)
    builder = _FakeCrewBuilder(directory, {
        "build": lambda attempt: {"files": {"src/main.py": "print('game')\n"} if attempt >= 2 else {}},
        "qa": lambda _attempt: {}, "release": lambda _attempt: {},
    })
    state, emitter = _run(_gate_workflow(), builder, run_id)
    assert state.status == "completed"
    assert builder.calls == {"build": 2, "qa": 2, "release": 1}
    assert state.node_outputs["gate"] == {"route": "pass", "rework_loops": 1}
    assert state.node_outputs["gate__gate"]["gate_passed"] is True
    assert state.node_outputs["build"]["artifact_contract"]["verified"] == ["src/main.py"]
    assert state.node_outputs["rework_feedback"]["missing"] == ["src/main.py"]
    assert any(kind == "FLOW_STATE_CHANGED" and payload.get("status") == "rework" and payload["targets"] == ["build"] for kind, payload in emitter.events)
    assert "Required deliverables" in builder.preambles["build"]["tbuild"] and "src/main.py" in builder.preambles["build"]["tbuild"]
    assert "completed_nodes" in state.model_dump() and state.completed_nodes.count("build") == 1
    assert all(isinstance(value, (str, int, float, bool, dict, list, type(None))) for value in builder.inputs[0].values())


def test_quality_gate_fails_the_run_when_rework_budget_is_exhausted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    builder = _FakeCrewBuilder(artifact_directory(TENANT, WORKSPACE, run_id), {
        "build": lambda _attempt: {}, "qa": lambda _attempt: {}, "release": lambda _attempt: {},
    })
    with pytest.raises(ValueError, match="after 2 rework loop"):
        _run(_gate_workflow(), builder, run_id)
    assert builder.calls["build"] == 3 and "release" not in builder.calls


def test_qa_crew_can_fail_the_gate_and_name_the_department(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    builder = _FakeCrewBuilder(artifact_directory(TENANT, WORKSPACE, run_id), {
        "build": lambda _attempt: {"files": {"src/main.py": "x = 1\n"}},
        "qa": lambda attempt: {"fields": {"gate_passed": attempt >= 2, "failing_department": "" if attempt >= 2 else "build"}},
        "release": lambda _attempt: {},
    })
    state, _ = _run(_gate_workflow(), builder, run_id)
    assert state.status == "completed" and builder.calls["build"] == 2 and state.node_outputs["gate"]["rework_loops"] == 1
