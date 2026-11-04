"""Phase 26: a failed run names the agent that failed, and a team cannot finish by claiming files it never wrote."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import BaseModel

from crews.tracking import track_agents
from flows.compiler import FlowCompiler
from hooks.claims import claim_material, claimed_files, deliverables_in, looks_like_file
from nexus_core_schema.artifacts import artifact_directory
from nexus_core_schema.models import CrewNodeSpec, WorkflowSpec
from test_phase17_studio import TENANT, WORKSPACE, _agent, _crew_node, _Emitter, _MemoryCheckpoints, _task, _workflow


class _Parsed(BaseModel):
    parsed_text: str = "| 1 | 1 |\n| 2 | 4 |"


class _Summary(BaseModel):
    summary_text: str = "Squares of one to five grow quickly."


class _Exported(BaseModel):
    exported_filename: str = "summary.md"


def _team() -> WorkflowSpec:
    node = _crew_node("work")
    node["agents"] = [_agent("parser").model_copy(update={"role": "Parser"}).model_dump(mode="json"), _agent("writer").model_copy(update={"role": "Writer"}).model_dump(mode="json")]
    node["tasks"] = [_task("t_parse", "parser").model_dump(mode="json"), _task("t_summary", "writer").model_dump(mode="json"), _task("t_export", "writer").model_dump(mode="json")]
    return _workflow([{"id": "start", "kind": "start"}, node], [{"source": "start", "target": "work"}])


class _Builder:
    """A crew whose agents run one after another; one can be told to fail, and one to write its file."""

    def __init__(self, directory: Path, claimed: str = "summary.md", fail_role: str | None = None, write: bool = False) -> None:
        self.directory, self.claimed, self.fail_role, self.write = directory, claimed, fail_role, write

    def build(self, node: CrewNodeSpec, _overrides: Any = None, _preambles: Any = None) -> Any:
        builder = self
        agents = []
        for spec in node.agents:
            def execute_task(task: Any = None, *, role: str = spec.role) -> str:
                if role == builder.fail_role:
                    raise RuntimeError("model call failed")
                return "ok"
            agents.append(SimpleNamespace(role=spec.role, execute_task=execute_task))

        class Crew:
            def __init__(self) -> None:
                self.agents = agents

            async def kickoff_async(self, inputs: dict[str, Any]) -> Any:
                for item in agents:
                    item.execute_task("task")
                if builder.write:
                    (builder.directory / builder.claimed).parent.mkdir(parents=True, exist_ok=True)
                    (builder.directory / builder.claimed).write_text("# written by the agent")
                final = _Exported(exported_filename=builder.claimed)
                return SimpleNamespace(pydantic=final, tasks_output=[SimpleNamespace(pydantic=item) for item in (_Parsed(), _Summary(), final)], token_usage=None)

        return SimpleNamespace(crew=Crew())


def _execute(builder: _Builder, run_id: Any) -> tuple[Any, _MemoryCheckpoints, _Emitter]:
    checkpoints, emitter = _MemoryCheckpoints(), _Emitter(run_id)
    compiler = FlowCompiler(cast(Any, checkpoints), cast(Any, emitter), cast(Any, None), cast(Any, builder))
    state = asyncio.run(compiler.compile(_team(), run_id, {"task": "Summarise squares.md"}).run())
    return state, checkpoints, emitter


def test_a_failed_run_records_the_agent_and_the_department(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    checkpoints, emitter = _MemoryCheckpoints(), _Emitter(run_id)
    compiler = FlowCompiler(cast(Any, checkpoints), cast(Any, emitter), cast(Any, None), cast(Any, _Builder(artifact_directory(TENANT, WORKSPACE, run_id), fail_role="Writer")))
    with pytest.raises(RuntimeError):
        asyncio.run(compiler.compile(_team(), run_id, {"task": "x"}).run())
    failure = checkpoints.failure
    assert failure is not None and failure["failed_agent_name"] == "Writer" and failure["failed_node_id"] == "work" and failure["error_type"] == "RuntimeError"
    message = [payload["message"] for kind, payload in emitter.events if kind == "RUN_FAILED"][0]
    assert "work" in message and failure["error_message"] in message


def test_a_claimed_document_that_was_never_written_is_rebuilt_from_what_the_team_wrote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    state, _, _ = _execute(_Builder(artifact_directory(TENANT, WORKSPACE, run_id)), run_id)
    assert state.status == "completed"
    written = (artifact_directory(TENANT, WORKSPACE, run_id) / "summary.md").read_text()
    assert "Squares of one to five grow quickly." in written and "| 2 | 4 |" in written, "the file holds the team's own text"
    contract = state.node_outputs["work"]["artifact_contract"]
    assert contract["recovered"] == ["summary.md"] and contract["passed"] is True, "the recovery is recorded, not hidden"


def test_a_claimed_file_that_exists_needs_no_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    state, _, _ = _execute(_Builder(artifact_directory(TENANT, WORKSPACE, run_id), write=True), run_id)
    contract = state.node_outputs["work"]["artifact_contract"]
    assert contract["verified"] == ["summary.md"] and contract["recovered"] == []
    assert (artifact_directory(TENANT, WORKSPACE, run_id) / "summary.md").read_text() == "# written by the agent"


def test_a_claimed_video_that_does_not_exist_fails_the_run_and_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    checkpoints, emitter = _MemoryCheckpoints(), _Emitter(run_id)
    compiler = FlowCompiler(cast(Any, checkpoints), cast(Any, emitter), cast(Any, None), cast(Any, _Builder(artifact_directory(TENANT, WORKSPACE, run_id), claimed="final_cut.mp4")))
    with pytest.raises(ValueError, match="did not deliver what it reported: final_cut.mp4 \\(missing\\)"):
        asyncio.run(compiler.compile(_team(), run_id, {"task": "x"}).run())
    assert not (artifact_directory(TENANT, WORKSPACE, run_id) / "final_cut.mp4").exists(), "media is never invented"
    assert checkpoints.failure is not None and checkpoints.failure["failed_node_id"] == "work" and checkpoints.failure["failed_agent_name"] == "Writer"


def test_file_claims_are_found_by_field_name_and_inputs_are_not_mistaken_for_deliverables() -> None:
    assert claimed_files([{"exported_filename": "summary.md", "summary": "text", "note": "x.md"}, {"files_written": ["a/b.csv", "not a file", "https://x.io/y.md", "../etc/passwd", ".hidden.md"]}]) == ["summary.md", "a/b.csv"]
    assert claimed_files([{"report_path": 5, "artifact": None}]) == [] and not looks_like_file("bad name.md") and looks_like_file("story/script.md")
    assert claim_material({"t": {"summary_text": "words", "exported_filename": "x.md"}}, {"parsed_text": "more", "files": ["x.md"]}) == {"summary_text": "words", "parsed_text": "more"}
    assert deliverables_in("Export the generated summary text to a markdown file named summary_of_squares.md using the report_exporter.") == ["summary_of_squares.md"]
    assert deliverables_in("Read the attached file. Then write the result to reports/final.csv.") == ["reports/final.csv"]
    assert deliverables_in("Parse the squares.md file to extract its text.") == []
    assert deliverables_in("Create a summary of squares.md for the board.") == []


def test_tracking_follows_real_nexusai_agents_and_never_touches_their_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    from crewai import Agent, Crew, Process, Task

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def execute_task(self: Any, task: Any, context: Any = None, tools: Any = None) -> str:
        if self.role == "Second":
            raise RuntimeError("model call failed")
        return "done"

    monkeypatch.setattr(Agent, "execute_task", execute_task)
    first = Agent(role="First", goal="g", backstory="b", llm="gpt-4o-mini")
    second = Agent(role="Second", goal="g", backstory="b", llm="gpt-4o-mini")
    crew = Crew(agents=[first, second], tasks=[Task(description="one", expected_output="x", agent=first), Task(description="two", expected_output="x", agent=second)], process=Process.sequential)
    tracker = track_agents(crew)
    assert first.role == "First" and second.role == "Second"
    with pytest.raises(Exception):  # noqa: B017 - the crew wraps the error; what matters is who the tracker blames
        crew.kickoff()
    assert tracker.failed == "Second" and tracker.culprit == "Second"
