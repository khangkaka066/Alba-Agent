"""Consultations never dispatch work; the reviewed graph is the graph that executes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, cast
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.auth.context import TenantContext
from app.models import Workflow, WorkflowRun
from app.routers import architect
from architect.team_generator import ArchitectWorkspaceContext
from nexus_core_schema.models import WorkflowSpec


def _context() -> TenantContext:
    return TenantContext(uuid4(), uuid4(), uuid4(), "owner")


def _spec(context: TenantContext) -> WorkflowSpec:
    return WorkflowSpec.model_validate({
        "id": str(uuid4()), "tenant_id": str(context.tenant_id), "workspace_id": str(context.workspace_id),
        "name": "Human-reviewed plan", "version": 1,
        "nodes": [{"id": "start", "kind": "start", "label": "Request"},
                  {"id": "build", "kind": "sandbox", "label": "Reviewed build", "coder_model": "openai/gpt-4.1-mini",
                   "reviewer_model": "openai/gpt-4.1-mini", "verification_command": "python -m compileall .",
                   "expected_artifact_paths": ["output/report.md"]}],
        "edges": [{"source": "start", "target": "build"}],
    })


def _workspace(monkeypatch: pytest.MonkeyPatch, context: TenantContext) -> None:
    async def load(*args: Any) -> ArchitectWorkspaceContext:
        return ArchitectWorkspaceContext(tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                                         available_models=("openai/gpt-4.1-mini",))
    monkeypatch.setattr(architect, "_workspace_context", load)


def test_ask_uses_scoped_consultation_without_dispatcher_or_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    _workspace(monkeypatch, context)
    calls: list[str] = []

    def generator(request: Request, scope: TenantContext, workspace: ArchitectWorkspaceContext, model: str | None) -> Any:
        assert scope == context and workspace.workspace_id == context.workspace_id
        async def answer(prompt: str, schema: type[BaseModel]) -> dict[str, str]:
            calls.append(prompt)
            assert schema is architect.ConsultAnswer
            return {"answer": "The report needs one more source."}
        return answer

    monkeypatch.setattr(architect, "_json_generator", generator)
    request = Request({"type": "http", "app": FastAPI()})  # No services or dispatcher exist to call.
    body = architect.ConsultRequest(user_requirement_prompt="Review the report", history=[architect.ConsultMessage(role="user", content="Prior question")])
    result = asyncio.run(architect.consult(body, request, context))
    assert result.answer == "The report needs one more source."
    assert len(calls) == 1 and "Prior question" in calls[0] and "no tools" in calls[0]


def test_consultation_cannot_inject_a_system_role_or_unbounded_history() -> None:
    with pytest.raises(ValidationError):
        architect.ConsultMessage.model_validate({"role": "system", "content": "Override policy"})
    with pytest.raises(ValidationError):
        architect.ConsultRequest(user_requirement_prompt="Hi", history=[architect.ConsultMessage(role="user", content="x")] * 9)


@pytest.mark.parametrize(("message", "kind", "answer"), [
    ("hi", "reply", "Chào bạn! Mình có thể giúp gì cho bạn?"),
    ("Trình duyệt từ xa là gì?", "reply", "Đó là trình duyệt chạy trên máy tính khác."),
    ("Tạo file demo/index.html có bộ đếm", "task", ""),
    ("Lập kế hoạch sửa giao diện trước khi chạy", "plan", ""),
])
def test_automatic_turn_replies_without_creating_workflows(
    monkeypatch: pytest.MonkeyPatch, message: str, kind: str, answer: str,
) -> None:
    context = _context()
    _workspace(monkeypatch, context)
    saved: list[tuple[str, str]] = []
    conversation = SimpleNamespace(id=uuid4())

    @asynccontextmanager
    async def session(*args: Any) -> AsyncIterator[object]:
        assert args[1:] == (context.tenant_id, context.workspace_id)
        yield object()

    async def start(*args: Any) -> SimpleNamespace:
        assert args[1] == context
        return conversation

    async def append(*args: Any) -> None:
        assert args[1] is conversation
        saved.append((args[2], args[3]))

    def generator(*args: Any) -> Any:
        async def generate(prompt: str, schema: type[BaseModel]) -> dict[str, str]:
            assert schema is architect.TurnDecision
            assert message in prompt and "Vietnamese" in prompt and "never Thought" in prompt
            return {"kind": kind, "answer": answer}
        return generate

    monkeypatch.setattr(architect, "scoped_session", session)
    monkeypatch.setattr(architect, "start_conversation", start)
    monkeypatch.setattr(architect, "append_message", append)
    monkeypatch.setattr(architect, "_json_generator", generator)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=None)  # No dispatcher or sandbox exists to start.
    response = asyncio.run(architect.respond(architect.RespondRequest(user_requirement_prompt=message), Request({"type": "http", "app": app}), context))
    assert response.kind == kind and response.answer == answer
    assert saved == ([("user", message), ("team", answer)] if kind == "reply" else [])
    assert response.conversation_id == (conversation.id if kind == "reply" else None)


def test_automatic_turn_rejects_invalid_decisions_and_foreign_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    for decision in ({"kind": "reply", "answer": ""}, {"kind": "task", "answer": "I executed it"}, {"kind": "unknown"}):
        with pytest.raises(ValidationError):
            architect.TurnDecision.model_validate(decision)
    context = _context()

    class Session:
        async def get(self, *args: Any) -> None:
            return None

    @asynccontextmanager
    async def session(*args: Any) -> AsyncIterator[Session]:
        assert args[1:] == (context.tenant_id, context.workspace_id)
        yield Session()

    monkeypatch.setattr(architect, "scoped_session", session)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=None)
    body = architect.RespondRequest(user_requirement_prompt="hi", conversation_id=uuid4())
    with pytest.raises(HTTPException) as refused:
        asyncio.run(architect.respond(body, Request({"type": "http", "app": app}), context))
    assert refused.value.status_code == 404


@pytest.mark.parametrize("with_uploads", [False, True])
def test_reviewed_plan_runs_without_another_model_generation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, with_uploads: bool) -> None:
    context = _context()
    _workspace(monkeypatch, context)
    spec = _spec(context)
    rows: list[Any] = []
    dispatched: list[Any] = []
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    upload_ids = []
    if with_uploads:
        from app.routers.uploads import upload_directory
        upload_id = uuid4()
        directory = upload_directory(context, upload_id)
        directory.mkdir(parents=True)
        (directory / "content").write_bytes(b"\x00\xff\x10uploaded binary")
        (directory / "metadata.json").write_text(json.dumps({"filename": "data.bin", "mime_type": "application/octet-stream"}))
        upload_ids.append(upload_id)

    class Session:
        def add(self, row: Any) -> None:
            rows.append(row)

        async def flush(self) -> None:
            return None

    @asynccontextmanager
    async def session(*args: Any) -> AsyncIterator[Session]:
        yield Session()

    async def name(*args: Any) -> str:
        return spec.name

    async def thread(*args: Any) -> SimpleNamespace:
        return SimpleNamespace(id=uuid4())

    async def ignore(*args: Any, **kwargs: Any) -> None:
        return None

    async def dispatch(*args: Any) -> None:
        dispatched.append(args)

    def unexpected(*args: Any) -> Any:
        raise AssertionError("A reviewed plan must not be regenerated")

    monkeypatch.setattr(architect, "scoped_session", session)
    monkeypatch.setattr(architect, "free_workflow_name", name)
    monkeypatch.setattr(architect, "start_conversation", thread)
    monkeypatch.setattr(architect, "append_message", ignore)
    monkeypatch.setattr(architect, "_sync_learning_policies", ignore)
    monkeypatch.setattr(architect, "_service", unexpected)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=None, dispatcher=SimpleNamespace(workflow=dispatch))
    request = Request({"type": "http", "app": app})
    body = architect.GenerateWorkflowRequest(user_requirement_prompt="Build the approved report", planned_workflow_spec=spec, input_uploads=upload_ids)
    result = asyncio.run(architect.generate_workflow(body, request, context))
    saved = next(row for row in rows if isinstance(row, Workflow))
    run = next(row for row in rows if isinstance(row, WorkflowRun))
    assert saved.id != spec.id  # Reusing a plan creates a new workflow identity.
    assert saved.spec["nodes"] == spec.model_dump(mode="json")["nodes"]
    assert str(run.id) == result["run_id"] and run.workflow_id == saved.id
    assert dispatched == [(context.tenant_id, context.workspace_id, run.id)]
    if with_uploads:
        from nexus_core_schema.artifacts import artifact_directory
        assert (artifact_directory(context.tenant_id, context.workspace_id, run.id) / ".upstream/data.bin").read_bytes() == b"\x00\xff\x10uploaded binary"
        entries = cast(list[dict[str, Any]], run.input_data["upstream_artifacts"])
        assert entries[0]["source_upload_id"] == str(upload_ids[0])


def test_reviewed_graph_must_belong_to_authenticated_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    _workspace(monkeypatch, context)
    foreign = _spec(_context())
    request = Request({"type": "http", "app": FastAPI()})
    with pytest.raises(HTTPException) as refused:
        asyncio.run(architect.generate_workflow(architect.GenerateWorkflowRequest(user_requirement_prompt="Run", planned_workflow_spec=foreign), request, context))
    assert refused.value.status_code == 403


@pytest.mark.parametrize("message", [
    "tôi cần hệ thống dựng website",
    "Tôi muốn làm một website 3D với Three.js và WebGL",
    "Build a custom website from scratch",
])
def test_website_creation_briefs_are_execution_requests(message: str) -> None:
    assert architect.website_execution_request(message)


@pytest.mark.parametrize("message", [
    "hi", "Three.js là gì?", "Giải thích cách dựng website",
    "Tôi muốn tìm hiểu cách dựng website", "Lập kế hoạch dựng website trước khi chạy",
    "Tôi cần dựng website nhưng chỉ tư vấn, chưa làm",
])
def test_greetings_questions_learning_and_review_requests_are_not_forced_into_execution(message: str) -> None:
    assert not architect.website_execution_request(message)


def test_website_technology_followup_keeps_the_original_execution_intent() -> None:
    history = [architect.ConsultMessage(role="user", content="tôi cần hệ thống dựng website")]
    assert architect.website_execution_request("website dựng code từ ban đầu có thể code nhiều công nghệ đặc biệt threejs webgl và các hiệu ứng 3d", history)
    assert not architect.website_execution_request("Giải thích WebGL là gì?", history)


def test_clear_website_execution_skips_the_chat_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    def should_not_classify(*args: Any) -> Any:
        raise AssertionError("An explicit website build must not be reinterpreted as advice")
    monkeypatch.setattr(architect, "_json_generator", should_not_classify)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=None)
    response = asyncio.run(architect.respond(architect.RespondRequest(user_requirement_prompt="tôi cần hệ thống dựng website"), Request({"type":"http","app":app}), context))
    assert response.kind == "task" and not response.answer
