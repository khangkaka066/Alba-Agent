from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from architect.units import MAX_UNITS, UnitsDraft, UnitDraft, build_units_workflow, unit_problems
from architect.team_generator import ArchitectWorkspaceContext, MetaArchitectService
from flows.compiler import FlowCompiler
from nexus_core_schema.models import NexusGenSandboxNodeSpec, WorkflowSpec
from nexusgen_bridge.sandbox_team import SandboxResult

TENANT, WORKSPACE = uuid4(), uuid4()
CONTRACT = "Every module imports SqlError from errors.py; tokenize(sql) returns (kind, value) pairs; parse(tokens) returns a dict statement."


def _unit(name: str, *paths: str) -> dict[str, Any]:
    return {"id": name, "label": f"Build {name}", "instructions": f"Build the {name} module exactly as the contract says.", "owned_paths": list(paths) or [f"{name}.py"]}


def _draft(*names: str) -> dict[str, Any]:
    return {"name": "Mini engine", "summary": "Independent modules then integration.", "contract": CONTRACT,
            "units": [_unit(name) for name in names], "integration_instructions": "Write engine.py that ties the modules together."}


def test_a_plan_needs_three_to_eight_units_with_distinct_ids() -> None:
    units = [UnitDraft(**_unit(name)) for name in ("a1", "b1")]
    assert any("3 to 8" in problem for problem in unit_problems(units))
    many = [UnitDraft(**_unit(f"u{index}")) for index in range(MAX_UNITS + 1)]
    assert any("3 to 8" in problem for problem in unit_problems(many))
    same = [UnitDraft(**_unit("aa", "aa.py")), UnitDraft(**_unit("aa", "bb.py")), UnitDraft(**_unit("cc"))]
    assert any("unique" in problem for problem in unit_problems(same))
    assert any("lowercase" in problem for problem in unit_problems([UnitDraft(**_unit("Bad-Id")), UnitDraft(**_unit("ok")), UnitDraft(**_unit("fine"))]))


def test_a_file_cannot_have_two_owners_and_a_folder_cannot_be_split() -> None:
    clash = [UnitDraft(**_unit("aa", "shared.py")), UnitDraft(**_unit("bb", "shared.py")), UnitDraft(**_unit("cc"))]
    assert any("owned by both" in problem for problem in unit_problems(clash))
    nested = [UnitDraft(**_unit("aa", "pkg")), UnitDraft(**_unit("bb", "pkg/inner.py")), UnitDraft(**_unit("cc"))]
    assert any("overlap" in problem for problem in unit_problems(nested))


def test_owned_paths_must_be_relative_non_test_files_that_do_not_collide_with_generated_tests() -> None:
    for bad in ("test_aa.py", "pkg/test_x.py", "/abs.py", "../up.py", ".hidden.py"):
        units = [UnitDraft(**_unit("aa", bad)), UnitDraft(**_unit("bb")), UnitDraft(**_unit("cc"))]
        assert any("not a valid owned path" in problem for problem in unit_problems(units)), bad
    units = [UnitDraft(**_unit("aa", "x.py")), UnitDraft(**_unit("bb", "y.py")), UnitDraft(**_unit("cc", "z.py"))]
    assert unit_problems(units) == []


def test_the_draft_model_rejects_an_overlapping_plan_with_the_reason() -> None:
    bad = _draft("aa", "bb", "cc")
    bad["units"][1]["owned_paths"] = ["aa.py"]
    with pytest.raises(ValidationError, match="owned by both"):
        UnitsDraft.model_validate(bad)


def _spec(*names: str) -> WorkflowSpec:
    return build_units_workflow(UnitsDraft.model_validate(_draft(*names)), workflow_id=uuid4(), tenant_id=TENANT, workspace_id=WORKSPACE,
                                   version=1, unit_model="openai/gpt-4.1-mini", integrate_model="openai/gpt-4.1")


def test_the_graph_fans_out_from_start_and_joins_all_units_into_the_integration_node() -> None:
    spec = FlowCompiler.validate(_spec("tok", "par", "sto", "evl"))
    nodes = {node.id: node for node in spec.nodes}
    units = [node for node in spec.nodes if node.id.startswith("unit_")]
    assert len(units) == 4 and all(isinstance(node, NexusGenSandboxNodeSpec) for node in units)
    assert {(edge.source, edge.target) for edge in spec.edges} == (
        {("start", node.id) for node in units} | {(node.id, "integrate") for node in units})
    integrate = nodes["integrate"]
    assert isinstance(integrate, NexusGenSandboxNodeSpec)
    assert integrate.join == "all" and set(integrate.mount_artifacts_from) == {node.id for node in units}
    assert integrate.min_added_tests == 2 and integrate.coder_model == "openai/gpt-4.1" and CONTRACT in integrate.coder_instructions
    for node in units:
        assert isinstance(node, NexusGenSandboxNodeSpec)
        assert node.on_unverified == "fail" and CONTRACT in node.coder_instructions and node.coder_model == "openai/gpt-4.1-mini"
    tokenizer = nodes["unit_tok"]
    assert isinstance(tokenizer, NexusGenSandboxNodeSpec) and tokenizer.expected_artifact_paths == ("tok.py", "test_tok.py")


def test_a_workflow_cannot_mount_files_from_a_node_that_does_not_exist_or_from_itself() -> None:
    spec = _spec("tok", "par", "sto")
    for target in ("ghost", "integrate"):
        nodes = tuple(node.model_copy(update={"mount_artifacts_from": (target,)}) if node.id == "integrate" else node for node in spec.nodes)
        with pytest.raises(ValidationError):
            WorkflowSpec.model_validate({**spec.model_dump(), "nodes": [node.model_dump() for node in nodes]})


def _service(replies: list[dict[str, Any]], seen: list[str]) -> MetaArchitectService:
    async def generate(prompt: str, output_model: type[BaseModel]) -> Any:
        seen.append(prompt)
        return replies.pop(0)

    return MetaArchitectService(generate, FlowCompiler.validate)


def test_rigor_units_plans_units_and_reports_the_level() -> None:
    seen: list[str] = []
    context = ArchitectWorkspaceContext(tenant_id=TENANT, workspace_id=WORKSPACE, available_models=("openai/gpt-4.1-mini", "openai/gpt-4.1"))
    spec, summary = asyncio.run(_service([_draft("tok", "par", "sto")], seen).generate_workflow("Build a mini SQL engine", context, rigor="units"))
    assert summary["level"] == "units" and summary["agent_count"] == 8 and "3 units" in summary["level_reason"]
    assert len(seen) == 1 and "independent units" in seen[0]
    assert [node.id for node in spec.nodes][-1] == "integrate"


def test_an_overlapping_first_plan_is_sent_back_with_the_reason_and_the_second_is_used() -> None:
    seen: list[str] = []
    bad = _draft("tok", "par", "sto")
    bad["units"][2]["owned_paths"] = ["tok.py"]
    context = ArchitectWorkspaceContext(tenant_id=TENANT, workspace_id=WORKSPACE, available_models=("openai/gpt-4.1-mini",))
    spec, _ = asyncio.run(_service([bad, _draft("tok", "par", "sto")], seen).generate_workflow("Build it", context, rigor="units"))
    assert len(seen) == 2 and "owned by both" in seen[1]
    assert len(spec.nodes) == 5


class _Checkpoints:
    async def create_run(self, state: Any) -> None: ...
    async def save(self, state: Any) -> None: ...
    async def record_failure(self, state: Any, failure: dict[str, Any]) -> None: ...


class _Emitter:
    def __init__(self, run_id: Any) -> None:
        self.tenant_id, self.workspace_id, self.run_id = TENANT, WORKSPACE, run_id

    async def emit(self, kind: Any, payload: dict[str, Any], node_id: str | None = None) -> None: ...


class _Runner:
    """Each unit node writes its declared files; the integration node records what it was given."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.integrate_inputs: dict[str, bytes] = {}
        self.integrate_task = ""
        self.written: dict[str, bytes] = {}

    async def run(self, task: str, node: NexusGenSandboxNodeSpec, emitter: Any, input_files: dict[str, bytes] | None = None) -> SandboxResult:
        if node.id == "integrate":
            self.integrate_inputs = dict(input_files or {})
            self.integrate_task = task
            return SandboxResult(summary="integrated", artifacts=(), exit_code=0, metrics={}, verification={"status": "verified"})
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.05)
        self.active -= 1
        for path in node.expected_artifact_paths:
            self.written[path] = f"# {node.id} {path}\n".encode()
        return SandboxResult(summary=f"{node.id} done", artifacts=tuple(node.expected_artifact_paths), exit_code=0, metrics={}, verification={"status": "verified"})


def test_the_integration_node_receives_every_units_files_after_all_units_finished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    runner = _Runner()

    async def read_file(tenant_id: Any, workspace_id: Any, run_id: Any, path: str) -> bytes:
        return runner.written[path]

    run_id = uuid4()
    compiler = FlowCompiler(cast(Any, _Checkpoints()), cast(Any, _Emitter(run_id)), cast(Any, runner), sandbox_file_reader=read_file)
    state = asyncio.run(compiler.compile(_spec("tok", "par", "sto"), run_id, {"task": "Build it"}).run())
    assert state.status == "completed"
    expected = {f"{name}.py" for name in ("tok", "par", "sto")} | {f"test_{name}.py" for name in ("tok", "par", "sto")}
    assert set(runner.integrate_inputs) == expected
    assert runner.integrate_inputs["tok.py"] == b"# unit_tok tok.py\n"
    assert "files_from_earlier_nodes" in runner.integrate_task and "test_par.py" in runner.integrate_task
    assert state.completed_nodes.index("integrate") == len(state.completed_nodes) - 1


@pytest.mark.xfail(strict=True, reason="All nodes of a run share one execution lock, one container and one working directory, so units run one at a time. "
                   "Running them at once needs a per-node working directory and a lock that lets sandbox nodes overlap; remove this mark then.")
def test_units_run_at_the_same_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    runner = _Runner()

    async def read_file(tenant_id: Any, workspace_id: Any, run_id: Any, path: str) -> bytes:
        return runner.written[path]

    run_id = uuid4()
    compiler = FlowCompiler(cast(Any, _Checkpoints()), cast(Any, _Emitter(run_id)), cast(Any, runner), sandbox_file_reader=read_file)
    asyncio.run(compiler.compile(_spec("tok", "par", "sto"), run_id, {"task": "Build it"}).run())
    assert runner.peak == 3
