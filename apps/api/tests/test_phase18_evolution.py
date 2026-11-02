"""Phase 18: bottleneck diagnosis, the five topology operators, mid-run spawning and generational fitness."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from flows.compiler import FlowCompiler
from nexus_core_schema.artifacts import artifact_directory
from nexus_core_schema.models import AutoGenSandboxNodeSpec, CrewNodeSpec, RouterNodeSpec, WorkflowSpec
from nexus_core_schema_templates.studios import STUDIO_BY_ID, build_studio_graph
from team_evolution import (
    BottleneckAnalyzer,
    BottleneckKind,
    DynamicSpawner,
    DynamicSpawnRequest,
    DynamicTeamMutatorTool,
    FitnessTracker,
    GenerationStats,
    HumanFeedback,
    InjectQuality,
    MutationError,
    OpKind,
    PruneOrMerge,
    RewireParallel,
    RunObservation,
    SpawnSpecialist,
    SplitOverloaded,
    TeamTopologyMutator,
    aggregate,
    extract_run_metrics,
    plan_operations,
    product_fitness,
)
from test_phase17_studio import TENANT, WORKSPACE, _Emitter, _FakeCrewBuilder, _MemoryCheckpoints, _spec

MODEL = "openai/gpt-4.1-mini"
MODELS = (MODEL, "anthropic/claude-sonnet-4")
TOOLS = {"report_exporter", "web_search", "chart_generator", "media_generation"}


def _studio(blueprint: str, rigor: str = "standard") -> WorkflowSpec:
    graph = build_studio_graph(STUDIO_BY_ID[blueprint], rigor, model=MODEL, director_model=MODEL, tools=TOOLS)  # type: ignore[arg-type]
    return _spec(graph)


def _crew(identifier: str, label: str, agents: list[tuple[str, str]], tasks: list[tuple[str, str, str, list[str]]],
          *, manager: str | None = None, goal: str = "do the work") -> dict[str, Any]:
    schema = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
    return {
        "id": identifier, "kind": "crew", "label": label, "process": "hierarchical" if manager else "sequential",
        "manager_agent_id": manager,
        "agents": [{"id": agent_id, "role": role, "goal": goal, "model": MODEL, "tier": "lead" if agent_id == manager else "specialist"} for agent_id, role in agents],
        "tasks": [{"id": task_id, "agent_id": agent_id, "description": text, "expected_output": "done", "output_schema": f"S_{task_id}",
                   "output_schema_json": schema, "expected_artifact_paths": paths} for task_id, agent_id, text, paths in tasks],
    }


def _graph(nodes: list[dict[str, Any]], edges: list[tuple[str, str]]) -> WorkflowSpec:
    return WorkflowSpec.model_validate({
        "id": str(uuid4()), "tenant_id": str(TENANT), "workspace_id": str(WORKSPACE), "name": "Evolving", "version": 1,
        "nodes": [{"id": "start", "kind": "start"}, *nodes],
        "edges": [{"source": "start", "target": edges[0][0]}, *({"source": a, "target": b} for a, b in edges)],
    })


def _compiles(spec: WorkflowSpec) -> None:
    """Valid under the schema AND buildable into a runnable Flow class."""
    FlowCompiler.validate(spec)
    run_id = uuid4()
    compiled = FlowCompiler(cast(Any, _MemoryCheckpoints()), cast(Any, _Emitter(run_id)), cast(Any, None), cast(Any, object())).compile(spec, run_id, {})
    assert compiled.flow_class is not None and len(spec.nodes) >= 2


def _observation(outputs: dict[str, Any], **extra: Any) -> RunObservation:
    return RunObservation(run_id=str(uuid4()), node_outputs=outputs, **extra)


def _contract(*, missing: tuple[str, ...] = (), verified: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"artifact_contract": {"passed": not missing, "missing": list(missing), "invalid": [], "verified": list(verified), "recovered": []}}


# --- 1. bottleneck analyzer -------------------------------------------------------------------------------------

def test_analyzer_names_the_missing_specialist_when_quality_review_cites_work_nobody_owns() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    gate = {"gate_passed": False, "failing_department": "story", "missing": [],
            "reasons": ["The narration needs audio ducking under the music and the subtitle timing drifts"]}
    report = BottleneckAnalyzer().analyze(spec, [_observation({"quality_gate__gate": gate, "story": _contract(verified=("story/script.md",))})])
    diagnosis = report.of_kind(BottleneckKind.MISSING_SPECIALIST_ROLE)[0]
    assert diagnosis.node_id == "story" and diagnosis.suggested_role == "Audio & Subtitle Sync Specialist"
    assert diagnosis.suggested_paths == ("media/sync_report.md",) and "ducking" in " ".join(diagnosis.evidence)


def test_analyzer_names_a_specialist_for_a_failed_deliverable_no_task_owns() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    report = BottleneckAnalyzer().analyze(spec, [_observation({"visual": _contract(missing=("visual/diagrams.md",))})])
    diagnosis = report.diagnoses[0]
    assert diagnosis.kind is BottleneckKind.MISSING_SPECIALIST_ROLE and diagnosis.node_id == "visual"
    assert diagnosis.suggested_role == "Diagrams Specialist" and diagnosis.suggested_paths == ("visual/diagrams.md",)


def test_analyzer_routes_owned_deliverable_failures_to_prompt_repair_until_they_repeat() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    failing = _observation({"story": _contract(missing=("story/script.md",))})
    once = BottleneckAnalyzer().analyze(spec, [failing]).diagnoses[0]
    assert once.kind is BottleneckKind.SKILL_OR_PROMPT_DEFICIT and once.route_to == "self_healing"
    twice = BottleneckAnalyzer().analyze(spec, [failing, _observation({"story": _contract(missing=("story/script.md",))})]).diagnoses[0]
    assert twice.repeat_count == 2 and twice.route_to == "topology"


def test_analyzer_flags_overloaded_nodes_and_unverified_code() -> None:
    paths = [f"design/doc_{index}.md" for index in range(6)]
    spec = _graph([
        _crew("big", "Big department", [("a", "Analyst")], [(f"t{i}", "a", f"write {p}", [p]) for i, p in enumerate(paths)]),
        _crew("coder", "Coders", [("c", "Programmer")], [("tc", "c", "write the code", ["src/main.py"])]),
    ], [("big", "coder")])
    partial = _observation({"big": _contract(missing=(paths[-1],), verified=tuple(paths[:-1])), "coder": _contract(missing=("src/main.py",))})
    report = BottleneckAnalyzer().analyze(spec, [partial])
    kinds = {item.node_id: item.kind for item in report.diagnoses}
    assert kinds["big"] is BottleneckKind.OVERLOADED_NODE_BOTTLENECK
    assert kinds["coder"] is BottleneckKind.MISSING_SANDBOX_OR_VERIFICATION_GATE


def test_analyzer_finds_idle_agents_and_negative_transfer() -> None:
    spec = _graph([_crew("dept", "Dept", [("lead", "Lead"), ("busy", "Busy"), ("other", "Other"), ("idle", "Idle")],
                         [("t1", "busy", "work", ["design/a.md"]), ("t2", "other", "more", ["design/b.md"])], manager="lead"),
                   _crew("after", "After", [("z", "Z")], [("tz", "z", "finish", [])])], [("dept", "after")])
    report = BottleneckAnalyzer().analyze(spec, [_observation({})], {"other": -0.6})
    found = {(item.agent_id, item.kind) for item in report.diagnoses}
    assert ("idle", BottleneckKind.REDUNDANT_OR_NEGATIVE_AGENT) in found and ("other", BottleneckKind.REDUNDANT_OR_NEGATIVE_AGENT) in found


def test_human_rejection_comment_is_diagnosed_like_a_quality_review() -> None:
    spec = _studio("full-stack-software-factory")
    feedback = HumanFeedback(node_id="backend", decision="denied", comment="There are no database migration scripts for the new tables")
    report = BottleneckAnalyzer().analyze(spec, [_observation({}, human_feedback=(feedback,))])
    assert any(item.kind is BottleneckKind.MISSING_SPECIALIST_ROLE and item.suggested_role == "Database Migration Engineer" for item in report.diagnoses)


# --- 2. the five mutation operators ----------------------------------------------------------------------------

def test_spawn_adds_a_tier_three_specialist_with_skills_tools_and_a_declared_deliverable() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    result = TeamTopologyMutator(TOOLS, MODELS).apply(spec, [SpawnSpecialist(
        target_node_id="visual", role="Technical Diagram Artist", goal="produce precise diagrams of the museum architecture",
        task_description="Draw and describe the architectural diagrams needed by the script and write them to the contract path.",
        expected_artifact_paths=("visual/diagrams.md",), rationale="no agent owns diagrams")])
    visual = next(node for node in result.spec.nodes if node.id == "visual")
    assert isinstance(visual, CrewNodeSpec) and result.spec.version == spec.version + 1 and result.spec.id != spec.id
    agent = next(item for item in visual.agents if item.role == "Technical Diagram Artist")
    assert agent.tier == "specialist" and "media_generation" in agent.tool_ids and "report_exporter" in agent.tool_ids
    task = next(item for item in visual.tasks if item.agent_id == agent.id)
    assert task.expected_artifact_paths == ("visual/diagrams.md",) and task.output_schema_json
    assert result.diff.added_agents["visual"] == ("Technical Diagram Artist",) and result.diff.modified_nodes == ("visual",)
    _compiles(result.spec)
    with pytest.raises(MutationError, match="already owned"):
        TeamTopologyMutator(TOOLS).apply(result.spec, [SpawnSpecialist(
            target_node_id="visual", role="Duplicate", goal="duplicate the diagrams", task_description="duplicate diagrams",
            expected_artifact_paths=("visual/diagrams.md",))])


def test_split_divides_an_overloaded_crew_into_parallel_crews_with_fan_out_and_fan_in() -> None:
    spec = _studio("full-game-development-studio", "full_studio")
    result = TeamTopologyMutator(TOOLS, MODELS).apply(spec, [SplitOverloaded(target_node_id="design", rationale="six deliverables in one crew")])
    ids = [node.id for node in result.spec.nodes]
    assert "design" not in ids and {"design_part1", "design_part2"} <= set(ids)
    parts = [node for node in result.spec.nodes if isinstance(node, CrewNodeSpec) and node.id.startswith("design_part")]
    original = next(node for node in spec.nodes if node.id == "design")
    assert isinstance(original, CrewNodeSpec)
    assert sorted(task.id for part in parts for task in part.tasks) == sorted(task.id for task in original.tasks)
    assert all(part.manager_agent_id == original.manager_agent_id and part.process == "hierarchical" for part in parts)
    forward = {(edge.source, edge.target) for edge in result.spec.edges if not edge.loop_back}
    assert {("direction", "design_part1"), ("direction", "design_part2")} <= forward
    assert {("design_part1", "engineering"), ("design_part2", "engineering")} <= forward
    engineering = next(node for node in result.spec.nodes if node.id == "engineering")
    assert isinstance(engineering, AutoGenSandboxNodeSpec) and engineering.join == "all"
    assert len({(round(result.spec.layout[part.id].x), round(result.spec.layout[part.id].y)) for part in parts}) == 2
    assert result.spec.layout["design_part1"].x == result.spec.layout["design_part2"].x
    gate = next(node for node in result.spec.nodes if isinstance(node, RouterNodeSpec))
    assert {"rework_design_part1", "rework_design_part2"} <= {route.name for route in gate.routes}
    assert {edge.target for edge in result.spec.edges if edge.loop_back and edge.route and edge.route.startswith("rework_design")} == {"design_part1", "design_part2"}
    _compiles(result.spec)


def test_split_extracts_code_deliverables_into_a_verifying_sandbox() -> None:
    spec = _graph([
        _crew("build", "Build team", [("dev", "Developer")], [("t1", "dev", "write the service", ["src/app.py", "design/notes.md"])]),
        _crew("after", "After", [("z", "Z")], [("tz", "z", "finish", [])]),
    ], [("build", "after")])
    result = TeamTopologyMutator(TOOLS).apply(spec, [SplitOverloaded(target_node_id="build", mode="extract_sandbox")])
    sandbox = next(node for node in result.spec.nodes if node.id == "build_build")
    assert isinstance(sandbox, AutoGenSandboxNodeSpec) and sandbox.expected_artifact_paths == ("src/app.py",)
    assert "test -s src/app.py" in sandbox.verification_command and "compileall" in sandbox.verification_command
    crew = next(node for node in result.spec.nodes if node.id == "build")
    assert isinstance(crew, CrewNodeSpec) and crew.declared_artifact_paths() == ("design/notes.md",)
    forward = {(edge.source, edge.target) for edge in result.spec.edges}
    assert ("build", "build_build") in forward and ("build_build", "after") in forward and ("build", "after") not in forward
    _compiles(result.spec)


def test_inject_adds_a_critic_node_or_enables_swarm_consensus() -> None:
    spec = _studio("full-stack-software-factory")
    mutator = TeamTopologyMutator(TOOLS, MODELS)
    critic = mutator.apply(spec, [InjectQuality(target_node_id="backend", mode="critic")])
    node = next(item for item in critic.spec.nodes if item.id == "backend_critic")
    assert isinstance(node, CrewNodeSpec) and node.agents[0].role == "QA Critic" and node.tasks[0].expected_artifact_paths == ("qa/backend_critic_critique.md",)
    forward = {(edge.source, edge.target) for edge in critic.spec.edges}
    assert ("backend", "backend_critic") in forward and ("backend_critic", "implementation") in forward and ("backend", "implementation") not in forward
    _compiles(critic.spec)
    consensus = mutator.apply(spec, [InjectQuality(target_node_id="implementation", mode="consensus")])
    sandbox = next(item for item in consensus.spec.nodes if item.id == "implementation")
    assert isinstance(sandbox, AutoGenSandboxNodeSpec) and sandbox.consensus_config.enabled and len(sandbox.consensus_config.models) == 2
    assert {model.split("/")[0] for model in sandbox.consensus_config.models} == {"openai", "anthropic"}
    single = TeamTopologyMutator(TOOLS, (MODEL,)).apply(spec, [InjectQuality(target_node_id="backend", mode="consensus")])
    assert any(item.id == "backend_critic" for item in single.spec.nodes)
    _compiles(consensus.spec)


def test_prune_merges_an_agent_or_removes_an_idle_node() -> None:
    spec = _studio("full-game-development-studio", "full_studio")
    design = next(node for node in spec.nodes if node.id == "design")
    assert isinstance(design, CrewNodeSpec)
    merged = TeamTopologyMutator(TOOLS).apply(spec, [PruneOrMerge(
        target_node_id="design", agent_id="design_economy_designer", merge_into_agent_id="design_systems_designer")])
    after = next(node for node in merged.spec.nodes if node.id == "design")
    assert isinstance(after, CrewNodeSpec) and len(after.agents) == len(design.agents) - 1
    economy_task = next(task for task in after.tasks if task.expected_artifact_paths == ("design/economy.md",))
    assert economy_task.agent_id == "design_systems_designer" and merged.diff.removed_agents["design"] == ("Economy Designer",)
    with pytest.raises(MutationError, match="owns declared deliverables"):
        TeamTopologyMutator(TOOLS).apply(spec, [PruneOrMerge(target_node_id="design", agent_id="design_economy_designer")])
    with pytest.raises(MutationError, match="lead cannot be pruned"):
        TeamTopologyMutator(TOOLS).apply(spec, [PruneOrMerge(target_node_id="design", agent_id=design.manager_agent_id)])
    chain = _graph([_crew("a", "A", [("aa", "A")], [("ta", "aa", "do a", ["design/a.md"])]),
                    _crew("filler", "Filler summariser", [("f", "F")], [("tf", "f", "summarise", [])]),
                    _crew("c", "C", [("cc", "C")], [("tc", "cc", "do c", ["design/c.md"])])], [("a", "filler"), ("filler", "c")])
    removed = TeamTopologyMutator(TOOLS).apply(chain, [PruneOrMerge(target_node_id="filler")])
    assert "filler" not in {node.id for node in removed.spec.nodes} and ("a", "c") in {(e.source, e.target) for e in removed.spec.edges}
    assert removed.diff.removed_nodes == ("filler",)
    _compiles(merged.spec)
    _compiles(removed.spec)
    with pytest.raises(MutationError, match="declared deliverables"):
        TeamTopologyMutator(TOOLS).apply(chain, [PruneOrMerge(target_node_id="a")])


def test_rewire_parallelises_independent_steps_and_refuses_dependent_ones() -> None:
    nodes = [
        _crew("research", "Market research", [("r", "Researcher")], [("tr", "r", "research competitors", ["story/research.md"])]),
        _crew("legal", "Legal review", [("l", "Lawyer")], [("tl", "l", "check licences of the product", ["qa/legal.md"])]),
        _crew("report", "Report", [("w", "Writer")], [("tw", "w", "write the report", ["release/report.md"])]),
    ]
    spec = _graph(nodes, [("research", "legal"), ("legal", "report")])
    mutator = TeamTopologyMutator(TOOLS)
    assert mutator.find_parallelizable(spec) == ["legal"]
    result = mutator.apply(spec, [RewireParallel(target_node_id="legal")])
    forward = {(edge.source, edge.target) for edge in result.spec.edges}
    assert {("start", "research"), ("research", "report"), ("start", "legal"), ("legal", "report")} <= forward and ("research", "legal") not in forward
    report = next(node for node in result.spec.nodes if node.id == "report")
    assert isinstance(report, CrewNodeSpec) and report.join == "all"
    assert result.spec.layout["research"].x == result.spec.layout["legal"].x and result.spec.layout["research"].y != result.spec.layout["legal"].y
    _compiles(result.spec)
    dependent = _graph([nodes[0], _crew("legal", "Legal review", [("l", "Lawyer")], [("tl", "l", "review the research in story/research.md", ["qa/legal.md"])]), nodes[2]],
                       [("research", "legal"), ("legal", "report")])
    with pytest.raises(MutationError, match="depends on"):
        mutator.apply(dependent, [RewireParallel(target_node_id="legal")])
    generic = _graph([nodes[0], _crew("legal", "Legal review", [("l", "Lawyer")], [("tl", "l", "review the upstream results", ["qa/legal.md"])]), nodes[2]],
                     [("research", "legal"), ("legal", "report")])
    assert mutator.find_parallelizable(generic) == []


def test_evolved_specs_stay_valid_across_a_chain_of_generations_and_skip_unsafe_operations() -> None:
    spec = _studio("full-game-development-studio", "full_studio")
    mutator = TeamTopologyMutator(TOOLS, MODELS)
    first = mutator.apply(spec, [
        SpawnSpecialist(target_node_id="design", role="Level Balance Designer", goal="model difficulty curves", task_description="Balance the difficulty curve.",
                        expected_artifact_paths=("design/balance_report.md",)),
        InjectQuality(target_node_id="narrative", mode="critic"),
        SplitOverloaded(target_node_id="art"),
    ], next_version=2)
    assert first.spec.version == 2 and len(first.applied) == 3 and [item.op for item in first.applied][0] is OpKind.SPAWN_SPECIALIST_AGENT
    second = mutator.apply(first.spec, [
        PruneOrMerge(target_node_id="audio", agent_id="audio_audio_integrator", merge_into_agent_id="audio_sound_designer"),
        SplitOverloaded(target_node_id="design"),
        SplitOverloaded(target_node_id="design"),
    ], strict=False)
    assert second.spec.version == 3 and len(second.applied) == 2 and len(second.skipped) == 1 and "design" in second.skipped[0]
    _compiles(first.spec)
    _compiles(second.spec)
    assert (spec.id, first.spec.id, second.spec.id) == (spec.id, first.spec.id, second.spec.id) and len({spec.id, first.spec.id, second.spec.id}) == 3


def test_planner_orders_operations_so_each_still_applies() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    gate = {"gate_passed": False, "failing_department": "story", "reasons": ["audio ducking and subtitle sync are missing"]}
    obs = _observation({"quality_gate__gate": gate, "visual": _contract(missing=("visual/diagrams.md",))}, run_seconds=300)
    report = BottleneckAnalyzer().analyze(spec, [obs])
    plan = plan_operations(report, spec, available_tools=TOOLS, available_models=MODELS)
    assert {op.op for op in plan.operations} >= {"SPAWN_SPECIALIST_AGENT"} and len(plan.operations) <= 6
    result = TeamTopologyMutator(TOOLS, MODELS).apply(spec, plan.operations)
    assert len(result.applied) == len(plan.operations)
    _compiles(result.spec)


# --- 3. mid-run spawning -----------------------------------------------------------------------------------------

def test_director_can_spawn_a_specialist_mid_run_and_persist_it() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    persisted: list[WorkflowSpec] = []

    async def persist(record: Any, evolved: WorkflowSpec) -> dict[str, Any]:
        persisted.append(evolved)
        return {"version": evolved.version, "status": "proposed"}

    spawner = DynamicSpawner(TeamTopologyMutator(TOOLS, MODELS), TOOLS, MODELS, persist_handler=persist)
    ran: list[str] = []

    async def executor(node: Any, task: str) -> dict[str, Any]:
        ran.append(node.id)
        return {"summary": "diagram written", "artifact_contract": {"verified": list(node.declared_artifact_paths())}}

    spawner.bind(spec, executor)
    tool = DynamicTeamMutatorTool(spawner)
    arguments = {"role": "Technical Diagram Artist", "goal": "produce architectural diagrams", "task": "Create the 3D diagram descriptions the script needs.",
                 "expected_artifact_paths": ["visual/diagrams.md"], "department_node_id": "visual", "persist": True, "rationale": "no one owns diagrams"}
    spawner.activate("direction")
    result = json.loads(asyncio.run(tool._arun(**arguments)))
    assert result["kind"] == "specialist" and result["paths"] == ["visual/diagrams.md"] and result["persisted"]["status"] == "proposed"
    assert ran and ran[0].startswith("dyn_") and result["result"]["artifact_contract"]["verified"] == ["visual/diagrams.md"]
    visual = next(node for node in persisted[0].nodes if node.id == "visual")
    assert isinstance(visual, CrewNodeSpec) and any(agent.role == "Technical Diagram Artist" for agent in visual.agents)
    _compiles(persisted[0])
    blocked = json.loads(asyncio.run(tool._arun(**arguments)))
    assert "already owned" in blocked["error"]


def test_dynamic_spawning_is_limited_to_directors_and_leads_and_to_a_per_run_budget() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    spawner = DynamicSpawner(TeamTopologyMutator(TOOLS), TOOLS, MODELS, max_spawns=2)

    async def executor(node: Any, task: str) -> dict[str, Any]:
        return {"summary": "ok"}

    spawner.bind(spec, executor)
    request = DynamicSpawnRequest(role="Helper", goal="help out", task="Help out with the work.", expected_artifact_paths=["media/helper_0.md"])
    with pytest.raises(MutationError, match="only available while"):
        asyncio.run(spawner.spawn(request))
    spawner.activate("start")
    with pytest.raises(MutationError, match="director or department lead"):
        asyncio.run(spawner.spawn(request))
    spawner.activate("direction")
    asyncio.run(spawner.spawn(request))
    asyncio.run(spawner.spawn(request.model_copy(update={"expected_artifact_paths": ["media/helper_1.md"]})))
    with pytest.raises(MutationError, match="already spawned 2"):
        asyncio.run(spawner.spawn(request.model_copy(update={"expected_artifact_paths": ["media/helper_2.md"]})))
    spawner.activate("direction")
    sandbox = DynamicSpawner(TeamTopologyMutator(TOOLS), TOOLS, MODELS)
    sandbox.bind(spec, executor)
    sandbox.activate("direction")
    ok = asyncio.run(sandbox.spawn(DynamicSpawnRequest(kind="sandbox", role="FFmpeg audio ducking", goal="duck the music under narration",
                                                       task="Write the ducking filter graph.", expected_artifact_paths=["media/ducking.txt"], persist=False)))
    assert ok["kind"] == "sandbox" and ok["persisted"] is None
    with pytest.raises(MutationError, match="Only specialists"):
        asyncio.run(sandbox.spawn(DynamicSpawnRequest(kind="sandbox", role="One more", goal="more work please", task="Do more work.",
                                                      expected_artifact_paths=["media/more.txt"], persist=True)))


class _SpawningBuilder(_FakeCrewBuilder):
    """The director's crew calls the dynamic tool while running, exactly as an agent would."""

    def __init__(self, directory: Path, spawner: DynamicSpawner) -> None:
        super().__init__(directory, {"direction": lambda _a: {}, "dyn": lambda _a: {"files": {"visual/diagrams.md": "# Diagrams\nA labelled floor plan.\n"}}})
        self.spawner = spawner
        self.tool_result: dict[str, Any] = {}

    def build(self, node: CrewNodeSpec, _overrides: Any = None, preambles: dict[str, str] | None = None) -> Any:
        if node.id.startswith("dyn_"):
            self.behaviours[node.id] = self.behaviours["dyn"]
        elif node.id not in self.behaviours:
            self.behaviours[node.id] = lambda _attempt: {}
        built = super().build(node, _overrides, preambles)
        if node.id != "direction":
            return built
        inner, builder = built.crew, self

        class DirectorCrew:
            async def kickoff_async(self, inputs: dict[str, Any]) -> Any:
                builder.tool_result = json.loads(await DynamicTeamMutatorTool(builder.spawner)._arun(
                    role="Technical Diagram Artist", goal="produce architectural diagrams of the venue",
                    task="Write the floor plan diagram the script requires.", expected_artifact_paths=["visual/diagrams.md"],
                    department_node_id="visual", persist=False))
                return await inner.kickoff_async(inputs)

        return type("Built", (), {"crew": DirectorCrew()})()


def test_compiled_run_executes_a_mid_run_specialist_and_records_it_in_the_director_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    spec = _studio("cinematic-video-documentary-studio")
    run_id = uuid4()
    spawner = DynamicSpawner(TeamTopologyMutator(TOOLS), TOOLS, MODELS)
    builder = _SpawningBuilder(artifact_directory(TENANT, WORKSPACE, run_id), spawner)
    emitter = _Emitter(run_id)
    # Run only the start and the director's crew so no other department is needed.
    mini = WorkflowSpec.model_validate({**spec.model_dump(mode="json"), "nodes": [n.model_dump(mode="json") for n in spec.nodes if n.id in ("start", "direction")],
                                        "edges": [{"source": "start", "target": "direction"}], "layout": {}})
    compiler = FlowCompiler(cast(Any, _MemoryCheckpoints()), cast(Any, emitter), cast(Any, None), cast(Any, builder), dynamic_spawner=spawner)
    state = asyncio.run(compiler.compile(mini, run_id, {"task": "Make the museum film"}).run())
    assert state.status == "completed"
    assert builder.tool_result["kind"] == "specialist" and builder.tool_result["result"]["artifact_contract"]["verified"] == ["visual/diagrams.md"]
    assert (artifact_directory(TENANT, WORKSPACE, run_id) / "visual" / "diagrams.md").is_file()
    spawned = state.node_outputs["direction"]["dynamic_team"]
    assert len(spawned) == 1 and spawned[0]["role"] == "Technical Diagram Artist" and spawned[0]["department"] == "visual"
    assert any(kind == "TOOL_INVOKED" and payload.get("tool") == "dynamic_team_mutator" for kind, payload in emitter.events)


# --- 4. fitness, generations and rollback ---------------------------------------------------------------------

def _stats(**overrides: Any) -> GenerationStats:
    base: dict[str, Any] = {"runs": 2, "artifact_completeness": 0.9, "quality": 0.8, "human_rating": None, "cost_usd": 1.0, "latency_seconds": 100.0}
    return GenerationStats(**{**base, **overrides})


def test_fitness_follows_the_published_weighting() -> None:
    parent = _stats()
    assert product_fitness(parent, parent) == pytest.approx(0.45 * 0.9 + 0.35 * 0.8 + 0.20 * 1.0)
    reviewed = _stats(human_rating=0.6)
    assert product_fitness(reviewed, parent) == pytest.approx(0.45 * 0.9 + 0.35 * 0.7 + 0.20 * 1.0)
    twice_as_costly = _stats(cost_usd=2.0, latency_seconds=200.0)
    assert product_fitness(twice_as_costly, parent) == pytest.approx(0.45 * 0.9 + 0.35 * 0.8 + 0.20 * 0.5)
    assert 0.0 <= product_fitness(_stats(artifact_completeness=0, quality=0, cost_usd=1e9), parent) <= 1.0


def test_run_metrics_measure_artifact_completeness_quality_and_review() -> None:
    spec = _studio("cinematic-video-documentary-studio")
    declared = [(node.id, path) for node in spec.nodes if isinstance(node, (CrewNodeSpec, AutoGenSandboxNodeSpec)) for path in node.declared_artifact_paths()]
    outputs: dict[str, Any] = {}
    for node_id, path in declared[:-1]:
        outputs.setdefault(node_id, {"artifact_contract": {"verified": [], "recovered": []}})["artifact_contract"]["verified"].append(path)
    outputs["quality_gate__gate"] = {"gate_passed": True}
    outputs["quality_gate__loops"] = 1
    metrics = extract_run_metrics(spec, "completed", outputs, ["start"], ["allowed_once", "denied"], cost_usd=0.5, latency_seconds=42)
    assert metrics.completeness == pytest.approx((len(declared) - 1) / len(declared))
    assert metrics.qa_score == pytest.approx(0.75) and metrics.human_rating == pytest.approx(0.5)
    assert metrics.cost_usd == 0.5 and metrics.completed
    recovered: dict[str, Any] = {}
    for node_id, path in declared:
        recovered.setdefault(node_id, {"artifact_contract": {"verified": [], "recovered": []}})["artifact_contract"]["recovered"].append(path)
    assert extract_run_metrics(spec, "completed", recovered, []).completeness == pytest.approx(0.75)
    failed = extract_run_metrics(spec, "failed", {}, ["start"])
    assert failed.completeness == 0.0 and failed.qa_score == 0.0 and not failed.completed


def test_a_worse_generation_is_rolled_back_but_a_better_or_comparable_one_is_kept() -> None:
    tracker = FitnessTracker()
    parent = _stats(artifact_completeness=0.9, quality=0.85)
    worse = _stats(artifact_completeness=0.6, quality=0.5, cost_usd=1.5, latency_seconds=160)
    decision = tracker.evaluate(worse, parent, parent)
    assert decision.rollback and decision.child_fitness < decision.parent_fitness - 0.05 and "fell more than" in decision.reason
    assert not tracker.evaluate(_stats(artifact_completeness=0.95, quality=0.9), parent, parent).rollback
    assert not tracker.evaluate(_stats(artifact_completeness=0.89, quality=0.84), parent, parent).rollback
    assert not tracker.evaluate(None, parent, parent).rollback
    assert not tracker.evaluate(_stats(runs=0), parent, parent).rollback
