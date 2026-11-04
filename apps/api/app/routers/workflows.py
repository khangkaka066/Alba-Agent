"""Workflow CRUD, Git import/export, execution, and tenant-scoped SSE."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import TenantContext, require_role
from app.models import AuditLog, ConversationMessage, LearningPolicy, TaskConversation, RunCheckpoint, Workflow, WorkflowRun
from app.models.scope import scoped_session
from app.handoff import carry_upstream
from app.routers.common import conflict, get_services, not_found
from app.routers.conversations import append_message, start_conversation
from nexus_core_schema.models import NexusGenSandboxNodeSpec, WorkflowSpec
from verification import is_compile_only
from nexus_core_schema.models import RuntimeEvent
from flows.compiler import FlowCompiler
from nexus_core_schema.artifacts import artifact_directory, artifact_file, list_artifacts, MEDIA_TYPES

router = APIRouter(tags=["workflows"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]
RUN = Annotated[TenantContext, Depends(require_role("builder", "run"))]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_data: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    run_id: UUID
    workflow_id: UUID
    status: str


def _validate_executable_graph(spec: WorkflowSpec) -> None:
    """Reject unreachable nodes, implicit cycles and loop-back edges that break the loop contract."""
    FlowCompiler.validate(spec)
    start = next(node.id for node in spec.nodes if node.kind == "start")
    if any(edge.target == start for edge in spec.edges):
        raise ValueError("Start node cannot have incoming edges")


def _parse_spec(raw: bytes, file_format: str) -> WorkflowSpec:
    if not raw or len(raw) > 1_048_576:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Workflow document must be at most 1 MiB")
    try:
        text = raw.decode("utf-8")
        data = json.loads(text) if file_format == "json" else yaml.safe_load(text)
        spec = WorkflowSpec.model_validate(data)
        _validate_executable_graph(spec)
        return spec
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError, ValueError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Workflow document is invalid: {error}") from error


def _check_scope(spec: WorkflowSpec, context: TenantContext) -> None:
    if (spec.tenant_id, spec.workspace_id) != (context.tenant_id, context.workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Workflow scope does not match authenticated workspace")
    try:
        _validate_executable_graph(spec)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error


async def _sync_learning_policies(session: Any, spec: WorkflowSpec, context: TenantContext) -> None:
    """Persist canvas edges as workspace policies in the same RLS transaction."""
    for edge in spec.learning_edges:
        row = await session.scalar(select(LearningPolicy).where(
            LearningPolicy.source_agent_id == edge.source_agent_id,
            LearningPolicy.target_agent_id == edge.target_agent_id,
        ).with_for_update())
        fields = {
            "propagation_scope": str(getattr(edge.scope, "value", edge.scope)),
            "allow_heuristics": edge.allow_heuristics,
            "allow_code_patterns": edge.allow_code_patterns,
            "require_human_approval": edge.require_human_approval,
            "allowed": True,
        }
        if row is None:
            session.add(LearningPolicy(
                tenant_id=context.tenant_id, workspace_id=context.workspace_id,
                source_agent_id=edge.source_agent_id, target_agent_id=edge.target_agent_id,
                source_domain_tags=[], target_domain_tags=[], **fields,
            ))
        else:
            for key, value in fields.items():
                setattr(row, key, value)


@router.get("/api/v1/workflows", response_model=list[WorkflowSpec])
async def list_workflows(request: Request, context: READ) -> list[WorkflowSpec]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(Workflow).order_by(Workflow.name, Workflow.version))).all()
        return [WorkflowSpec.model_validate(row.spec) for row in rows]


@router.post("/api/v1/workflows/validate")
async def validate_workflow(spec: WorkflowSpec, context: BUILD) -> dict[str, object]:
    _check_scope(spec, context)
    # A compile-only command is never counted as evidence; the runtime discovers executable tests instead.
    warnings = [
        f"{node.id}: verification_command only compiles; it is not evidence, so results rely on discovered tests"
        for node in spec.nodes if isinstance(node, NexusGenSandboxNodeSpec) and is_compile_only(node.verification_command)
    ]
    return {"valid": True, "node_count": len(spec.nodes), "edge_count": len(spec.edges), "warnings": warnings}


@router.post("/api/v1/workflows/import", status_code=status.HTTP_201_CREATED, response_model=WorkflowSpec)
async def import_workflow(
    request: Request,
    context: BUILD,
    file_format: str = "json",
) -> WorkflowSpec:
    if file_format not in ("json", "yaml"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Format must be json or yaml")
    spec = _parse_spec(await request.body(), file_format)
    _check_scope(spec, context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = Workflow(
            id=spec.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            name=spec.name, version=spec.version, spec=spec.model_dump(mode="json"),
        )
        session.add(row)
        try:
            await session.flush()
            await _sync_learning_policies(session, spec, context)
        except IntegrityError as error:
            raise conflict("Workflow ID or version already exists") from error
    return spec


@router.post("/api/v1/workflows", status_code=status.HTTP_201_CREATED, response_model=WorkflowSpec)
async def create_workflow(spec: WorkflowSpec, request: Request, context: BUILD) -> WorkflowSpec:
    _check_scope(spec, context)
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        session.add(Workflow(
            id=spec.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            name=spec.name, version=spec.version, spec=spec.model_dump(mode="json"),
        ))
        try:
            await session.flush()
            await _sync_learning_policies(session, spec, context)
        except IntegrityError as error:
            raise conflict("Workflow ID or version already exists") from error
    return spec


@router.get("/api/v1/workflows/{workflow_id}/export")
async def export_workflow(workflow_id: UUID, file_format: str, request: Request, context: READ) -> Response:
    if file_format not in ("json", "yaml"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Format must be json or yaml")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(Workflow, workflow_id)
        if row is None:
            raise not_found("Workflow is not visible in this workspace")
        spec = WorkflowSpec.model_validate(row.spec)
    data = spec.model_dump(mode="json")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n" if file_format == "json" else yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    media = "application/json" if file_format == "json" else "application/yaml"
    return Response(text, media_type=media, headers={"Content-Disposition": f'attachment; filename="{workflow_id}.{file_format}"'})


@router.get("/api/v1/workflows/{workflow_id}", response_model=WorkflowSpec)
async def get_workflow(workflow_id: UUID, request: Request, context: READ) -> WorkflowSpec:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(Workflow, workflow_id)
        if row is None:
            raise not_found("Workflow is not visible in this workspace")
        return WorkflowSpec.model_validate(row.spec)


@router.put("/api/v1/workflows/{workflow_id}", response_model=WorkflowSpec)
async def update_workflow(workflow_id: UUID, spec: WorkflowSpec, request: Request, context: BUILD) -> WorkflowSpec:
    _check_scope(spec, context)
    if spec.id != workflow_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Workflow ID cannot change")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
        if row is None:
            raise not_found("Workflow is not visible in this workspace")
        run_count = await session.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id))
        if run_count:
            raise conflict("Workflow definitions with run history are immutable; create a new version")
        row.name, row.version, row.spec = spec.name, spec.version, spec.model_dump(mode="json")
        await _sync_learning_policies(session, spec, context)
    return spec


@router.delete("/api/v1/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_workflow(workflow_id: UUID, request: Request, context: BUILD) -> Response:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
        if row is None:
            raise not_found("Workflow is not visible in this workspace")
        run_count = await session.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id))
        if run_count:
            raise conflict("Workflow definitions with run history cannot be deleted")
        await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# `/run` is accepted as an alias of `/runs`: scripts and clients in the wild use both spellings.
@router.post("/api/v1/workflows/{workflow_id}/run", status_code=status.HTTP_202_ACCEPTED, response_model=RunResponse, include_in_schema=False)
@router.post("/api/v1/workflows/{workflow_id}/runs", status_code=status.HTTP_202_ACCEPTED, response_model=RunResponse)
async def start_workflow(workflow_id: UUID, body: RunRequest, request: Request, context: RUN) -> RunResponse:
    services = get_services(request)
    if len(json.dumps(body.input_data, separators=(",", ":")).encode()) > 1_048_576:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Workflow input exceeds 1 MiB")
    run_id = uuid4()
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        workflow = await session.get(Workflow, workflow_id)
        if workflow is None:
            raise not_found("Workflow is not visible in this workspace")
        spec = WorkflowSpec.model_validate(workflow.spec)
        _check_scope(spec, context)
        session.add(WorkflowRun(
            id=run_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            workflow_id=workflow_id, status="queued", input_data=body.input_data,
        ))
        session.add(AuditLog(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            actor_id=context.user_id, action="workflow.run_queued", target_type="workflow_run",
            target_id=run_id, details={"workflow_id": str(workflow_id)},
        ))
        # Every run belongs to a thread, so it can be reopened and deleted like a task started from the prompt bar.
        task = body.input_data.get("task")
        conversation = await start_conversation(session, context, task if isinstance(task, str) and task.strip() else workflow.name)
        if isinstance(task, str) and task.strip():
            await append_message(session, conversation, "user", task)
        await append_message(session, conversation, "team", workflow.name, run_id=run_id, workflow_id=workflow_id)
    try:
        await services.dispatcher.workflow(context.tenant_id, context.workspace_id, run_id)
    except Exception as error:
        async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
            row = await session.get(WorkflowRun, run_id)
            if row is not None:
                row.status = "failed"
                row.finished_at = datetime.now(timezone.utc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Workflow queue is unavailable") from error
    return RunResponse(run_id=run_id, workflow_id=workflow_id, status="queued")


async def _conversation_ids(session: AsyncSession, run_ids: list[UUID]) -> dict[UUID, str]:
    if not run_ids:
        return {}
    rows = (await session.execute(select(ConversationMessage.run_id, ConversationMessage.conversation_id).where(ConversationMessage.run_id.in_(run_ids)))).all()
    return {run_id: str(conversation_id) for run_id, conversation_id in rows if run_id is not None}


@router.get("/api/v1/runs")
async def list_runs(request: Request, context: READ, workflow_id: UUID | None = None) -> list[dict[str, Any]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        statement = select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(50)
        if workflow_id is not None:
            if await session.get(Workflow, workflow_id) is None:
                raise not_found("Workflow is not visible in this workspace")
            statement = statement.where(WorkflowRun.workflow_id == workflow_id)
        rows = (await session.scalars(statement)).all()
        conversations = await _conversation_ids(session, [row.id for row in rows])
    return [{"id": str(row.id), "workflow_id": str(row.workflow_id), "status": row.status, "conversation_id": conversations.get(row.id),
             "failure": row.failure, "created_at": row.created_at, "artifacts": list_artifacts(context.tenant_id, context.workspace_id, row.id)}
            for row in rows]


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # `step` continues the same run from its last good checkpoint; `team` starts the same team again from the beginning.
    mode: Literal["step", "team"] = "step"


@router.post("/api/v1/runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_run(run_id: UUID, body: RetryRequest, request: Request, context: RUN) -> dict[str, Any]:
    services = get_services(request)
    new_run = uuid4()
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        run = await session.get(WorkflowRun, run_id)
        if run is None:
            raise not_found("Run is not visible in this workspace")
        if run.status != "failed":
            raise conflict("Only a failed task can be retried")
        has_checkpoint = await session.scalar(select(RunCheckpoint.id).where(RunCheckpoint.run_id == run_id).limit(1)) is not None
        if body.mode == "team" or not has_checkpoint:
            inputs = dict(run.input_data)
            upstream = inputs.get("upstream_artifacts")
            if isinstance(upstream, list):
                inputs["upstream_artifacts"] = carry_upstream(context, run_id, new_run, [item for item in upstream if isinstance(item, dict)])
            session.add(WorkflowRun(id=new_run, tenant_id=context.tenant_id, workspace_id=context.workspace_id, workflow_id=run.workflow_id, status="queued", input_data=inputs))
            conversation_id = (await _conversation_ids(session, [run_id])).get(run_id)
            if conversation_id is not None:
                conversation = await session.get(TaskConversation, UUID(conversation_id))
                if conversation is not None:
                    await append_message(session, conversation, "team", "Retry: the same team starts again", run_id=new_run, workflow_id=run.workflow_id, meta={"retry_of": str(run_id)})
        session.add(AuditLog(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id, action="workflow.retry_requested",
            target_type="workflow_run", target_id=run_id, details={"mode": body.mode if has_checkpoint else "team", "new_run_id": str(new_run)},
        ))
    if body.mode == "step" and has_checkpoint:
        state = await services.checkpoints.load(context.tenant_id, context.workspace_id, run_id)
        state.status, state.active_node_id = "running", None  # nodes already completed are skipped when the run is replayed
        await services.checkpoints.save(state)
        target, mode = run_id, "step"
    else:
        target, mode = new_run, "team"
    try:
        await services.dispatcher.workflow(context.tenant_id, context.workspace_id, target)
    except Exception as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Workflow queue is unavailable") from error
    return {"run_id": str(target), "workflow_id": str(run.workflow_id), "mode": mode, "status": "running" if mode == "step" else "queued"}


@router.get("/api/v1/runs/{run_id}")
async def get_run(run_id: UUID, request: Request, context: READ) -> dict[str, object]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        run = await session.get(WorkflowRun, run_id)
        if run is None:
            raise not_found("Run is not visible in this workspace")
        checkpoint = await session.scalar(
            select(RunCheckpoint)
            .where(RunCheckpoint.run_id == run_id)
            .order_by(RunCheckpoint.sequence.desc())
            .limit(1)
        )
        state = checkpoint.state if checkpoint is not None else {}
        node_outputs = state.get("node_outputs")
        conversation_id = (await _conversation_ids(session, [run_id])).get(run_id)
        return {
            "id": str(run.id), "workflow_id": str(run.workflow_id), "status": run.status,
            "conversation_id": conversation_id, "failure": run.failure,
            "started_at": run.started_at, "finished_at": run.finished_at,
            "active_node_id": state.get("active_node_id"),
            "node_outputs": state.get("node_outputs", {}),
            "pending_approval_id": state.get("pending_approval_id"),
            "artifacts": list_artifacts(context.tenant_id, context.workspace_id, run_id,
                                        node_outputs if isinstance(node_outputs, dict) else None),
        }


@router.get("/api/v1/runs/{run_id}/artifacts")
async def run_artifacts(run_id: UUID, request: Request, context: READ) -> list[dict[str, Any]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(WorkflowRun, run_id) is None:
            raise not_found("Run is not visible in this workspace")
        checkpoint = await session.scalar(
            select(RunCheckpoint).where(RunCheckpoint.run_id == run_id)
            .order_by(RunCheckpoint.sequence.desc()).limit(1)
        )
        node_outputs = checkpoint.state.get("node_outputs") if checkpoint is not None else None
    return list_artifacts(context.tenant_id, context.workspace_id, run_id,
                          node_outputs if isinstance(node_outputs, dict) else None)


@router.get("/api/v1/runs/{run_id}/artifacts/{filename:path}")
async def download_run_artifact(run_id: UUID, filename: str, request: Request, context: READ) -> FileResponse:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(WorkflowRun, run_id) is None:
            raise not_found("Run is not visible in this workspace")
    try:
        path = artifact_file(artifact_directory(context.tenant_id, context.workspace_id, run_id), filename)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    if not path.is_file():
        raise not_found("Artifact is unavailable")
    mime_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=mime_type, filename=path.name,
                        content_disposition_type="inline" if mime_type.startswith(("video/", "audio/", "image/")) else "attachment")


@router.get("/api/v1/runs/{run_id}/stream")
async def stream_run(run_id: UUID, request: Request, context: READ) -> StreamingResponse:
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(WorkflowRun, run_id) is None:
            raise not_found("Run is not visible in this workspace")

    async def events() -> Any:
        pubsub = services.redis.pubsub()
        await pubsub.subscribe(f"run:{context.tenant_id}:{run_id}:events")
        last_heartbeat = time.monotonic()
        try:
            while not await request.is_disconnected():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and isinstance(message.get("data"), str):
                    event = RuntimeEvent.model_validate_json(message["data"])
                    if (event.tenant_id, event.workspace_id, event.run_id) != (context.tenant_id, context.workspace_id, run_id):
                        continue
                    yield f"id: {event.id}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"
                    if event.type in ("RUN_COMPLETED", "RUN_FAILED"):
                        break
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= 15:
                    yield ": keep-alive\n\n"
                    last_heartbeat = time.monotonic()
        finally:
            await pubsub.unsubscribe(f"run:{context.tenant_id}:{run_id}:events")
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
