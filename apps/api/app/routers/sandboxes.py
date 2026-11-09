"""Tenant-scoped virtual computer lifecycle and live output streams."""

from __future__ import annotations

import asyncio
import base64
import json
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from collections.abc import Coroutine, Callable
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.context import TenantContext, require_role, tenant_context, ROLE_RANK
from app.billing.plans import enforce_monthly_sandbox_quota, record_sandbox_usage
from app.models import PersistentBot, SandboxComputer, WorkflowRun
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from flows.compiler import PauseRequested
from nexus_computer_sandbox import ComputerAccess

class SandboxRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)
            except PermissionError as error:
                raise HTTPException(403, str(error)) from error
            except LookupError as error:
                raise HTTPException(404, str(error)) from error
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
            except asyncio.TimeoutError as error:
                raise HTTPException(504, "Sandbox operation timed out") from error
            except RuntimeError as error:
                raise HTTPException(503, str(error)) from error
        return guarded


router = APIRouter(route_class=SandboxRoute, prefix="/api/v1/sandboxes", tags=["sandboxes"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


class ComputerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visibility: str = Field(default="private", pattern="^(shared|private)$")
    provider: str | None = Field(default=None, pattern="^(docker|local|e2b|daytona|createos|boat)$")
    bot_id: UUID | None = None
    run_id: UUID | None = None


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1, max_length=16_384)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    background: bool = False


class BrowserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(navigate|click|fill|screenshot|extract|takeover|status)$")
    arguments: dict[str, str] = Field(default_factory=dict)


async def _computer_context(request: Request, context: TenantContext, computer_id: UUID) -> tuple[ComputerAccess, SandboxComputer]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(SandboxComputer, computer_id)
        if row is None:
            raise not_found("Computer is not visible in this workspace")
    return ComputerAccess(context.tenant_id, context.workspace_id, row.bot_id, row.run_id), row


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_computer(body: ComputerCreate, request: Request, context: BUILD) -> dict[str, object]:
    services = get_services(request)
    if body.visibility == "private" and body.bot_id is None and body.run_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Private computers require a bot or run owner")
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        if body.bot_id is not None and await session.get(PersistentBot, body.bot_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Computer bot is not in this workspace")
        if body.run_id is not None and await session.get(WorkflowRun, body.run_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Computer run is not in this workspace")
    access = ComputerAccess(context.tenant_id, context.workspace_id, body.bot_id, body.run_id)
    try:
        handle = await services.sandbox.create(access, body.visibility, body.provider)  # type: ignore[arg-type]
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Computer provider is unavailable") from error
    return {"id": str(handle.id), "provider": handle.provider, "visibility": handle.visibility, "status": "running"}


@router.get("")
async def list_computers(request: Request, context: READ) -> list[dict[str, object]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(SandboxComputer).order_by(SandboxComputer.created_at.desc()))).all()
        return [{"id": str(row.id), "provider": row.provider, "visibility": row.visibility, "status": row.status, "bot_id": str(row.bot_id) if row.bot_id else None, "run_id": str(row.run_id) if row.run_id else None} for row in rows]


@router.get("/{computer_id}")
async def get_computer(computer_id: UUID, request: Request, context: READ) -> dict[str, object]:
    access, row = await _computer_context(request, context, computer_id)
    try:
        await get_services(request).sandbox.get(access, computer_id)
    except LookupError as error:
        raise not_found() from error
    return {"id": str(row.id), "provider": row.provider, "visibility": row.visibility, "status": row.status}


@router.delete("/{computer_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def stop_computer(computer_id: UUID, request: Request, context: BUILD) -> Response:
    access, _ = await _computer_context(request, context, computer_id)
    try:
        await get_services(request).sandbox.terminate(access, computer_id)
    except LookupError as error:
        raise not_found() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{computer_id}/terminal")
async def execute_terminal(computer_id: UUID, body: TerminalRequest, request: Request, context: BUILD) -> dict[str, object]:
    services = get_services(request)
    await enforce_monthly_sandbox_quota(services.engine, context.tenant_id, context.workspace_id, Decimal(body.timeout_seconds))
    access, computer = await _computer_context(request, context, computer_id)

    async def sink(stream: str, content: str) -> None:
        return None

    async def guard(scope: ComputerAccess, boundary: str, command: str) -> None:
        coordinator = services.approvals(scope.tenant_id, scope.workspace_id, context.user_id)
        await coordinator.computer_guard(scope, boundary, command)

    try:
        result = await services.interactive.execute(
            access, computer_id, body.command, body.timeout_seconds, sink, body.background, guard,
        )
    except PauseRequested as error:
        return {"status": "paused", "approval_id": str(error).rsplit(": ", 1)[-1]}
    except PermissionError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    await record_sandbox_usage(services.engine, context.tenant_id, context.workspace_id, Decimal(str(result.elapsed_seconds)), run_id=computer.run_id)
    return {"status": "running" if result.process_id else "completed", "process_id": result.process_id, "snapshot_id": result.snapshot_id, "error_digest": result.error_digest, "exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr, "elapsed_seconds": result.elapsed_seconds}


@router.post("/{computer_id}/terminal/stream")
async def stream_terminal(computer_id: UUID, body: TerminalRequest, request: Request, context: BUILD) -> StreamingResponse:
    services = get_services(request)
    await enforce_monthly_sandbox_quota(services.engine, context.tenant_id, context.workspace_id, Decimal(body.timeout_seconds))
    access, computer = await _computer_context(request, context, computer_id)
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)

    async def sink(stream: str, content: str) -> None:
        await queue.put(f"event: {stream}\ndata: {json.dumps({'text': content})}\n\n")

    async def guard(scope: ComputerAccess, boundary: str, command: str) -> None:
        await services.approvals(scope.tenant_id, scope.workspace_id, context.user_id).computer_guard(scope, boundary, command)

    async def produce() -> None:
        try:
            result = await services.interactive.execute(
                access, computer_id, body.command, body.timeout_seconds, sink, body.background, guard,
            )
            await record_sandbox_usage(services.engine, context.tenant_id, context.workspace_id, Decimal(str(result.elapsed_seconds)), run_id=computer.run_id)
            await queue.put(f"event: result\ndata: {json.dumps({'exit_code': result.exit_code, 'artifacts': result.artifacts, 'process_id': result.process_id, 'snapshot_id': result.snapshot_id, 'error_digest': result.error_digest})}\n\n")
        except PauseRequested as error:
            await queue.put(f"event: approval_required\ndata: {json.dumps({'approval_id': str(error).rsplit(': ', 1)[-1], 'action': body.command, 'required_role': 'admin'})}\n\n")
        except Exception as error:
            await queue.put(f"event: error\ndata: {json.dumps({'error': type(error).__name__})}\n\n")
        finally:
            await queue.put(None)

    async def events() -> Any:
        producer = asyncio.create_task(produce())
        try:
            while not await request.is_disconnected():
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not producer.done():
                producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{computer_id}/files")
async def upload_computer_file(computer_id: UUID, path: str, request: Request, context: BUILD) -> dict[str, object]:
    access, _ = await _computer_context(request, context, computer_id)
    try:
        size = await get_services(request).sandbox.upload_stream(access, computer_id, path, request.stream())
    except ValueError as error:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "500 MiB" in str(error) else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(code, str(error)) from error
    return {"path": path, "size": size}


@router.get("/{computer_id}/files")
async def download_computer_file(computer_id: UUID, path: str, request: Request, context: READ) -> Response:
    access, _ = await _computer_context(request, context, computer_id)
    try:
        content = await get_services(request).sandbox.download(access, computer_id, path)
    except FileNotFoundError as error:
        raise not_found("Computer file is not present") from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{path.rsplit("/", 1)[-1]}"'})


@router.get("/{computer_id}/screen")
@router.get("/{computer_id}/screen/stream")
async def stream_screen(computer_id: UUID, request: Request, context: READ) -> StreamingResponse:
    access, _ = await _computer_context(request, context, computer_id)
    supervisor = get_services(request).sandbox

    async def frames() -> Any:
        async for frame in supervisor.screen_proxy(access, computer_id):
            if await request.is_disconnected():
                break
            yield f"event: screen_frame\ndata: {json.dumps({'png_base64': base64.b64encode(frame).decode('ascii')})}\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{computer_id}/browser")
async def browser_computer_action(computer_id: UUID, body: BrowserRequest, request: Request, context: BUILD) -> dict[str, str | None]:
    services = get_services(request)
    access, _ = await _computer_context(request, context, computer_id)

    async def guard(scope: ComputerAccess, boundary: str, action_name: str) -> None:
        await services.approvals(scope.tenant_id, scope.workspace_id, context.user_id).computer_guard(scope, boundary, action_name)

    try:
        arguments: dict[str, Any] = {key: value for key, value in body.arguments.items() if key not in {"human", "approved", "action", "timeout_seconds"}}
        if body.action in {"click", "fill"}:
            await guard(access, "external_action", f"Browser {body.action}")
            arguments["approved"] = True
        if body.action == "takeover":
            arguments["enabled"] = body.arguments.get("enabled") == "true"
        result = await services.interactive.browser(access, computer_id, body.action, arguments)
    except PauseRequested as error:
        raise HTTPException(status.HTTP_202_ACCEPTED, f"Approval required: {error}") from error
    return {"frame_png_base64": result.get("frame_png_base64")}



class TerminalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: str = Field(max_length=16_384)
    process_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ProcessControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(interrupt|stop)$")
    process_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


@router.get("/{computer_id}/terminal/status")
async def terminal_status(computer_id: UUID, request: Request, context: READ, after: int = 0) -> dict[str, Any]:
    access, _ = await _computer_context(request, context, computer_id)
    return await get_services(request).interactive.status(access, computer_id, max(0, after))


@router.get("/{computer_id}/terminal/events")
async def terminal_events(computer_id: UUID, request: Request, context: READ, after: int = 0) -> StreamingResponse:
    access, _ = await _computer_context(request, context, computer_id)
    service = get_services(request).interactive
    async def events() -> Any:
        cursor = max(0, after)
        while not await request.is_disconnected():
            row = await service.status(access, computer_id, cursor)
            for event in row.get("events", []):
                cursor = max(cursor, int(event["sequence"]))
                yield f"id: {cursor}\nevent: terminal\ndata: {json.dumps(event)}\n\n"
            yield f"event: session\ndata: {json.dumps({key: value for key, value in row.items() if key != 'events'})}\n\n"
            await asyncio.sleep(0.8)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{computer_id}/terminal/input")
async def terminal_input(computer_id: UUID, body: TerminalInput, request: Request, context: BUILD) -> dict[str, bool]:
    access, _ = await _computer_context(request, context, computer_id)
    await get_services(request).interactive.input(access, computer_id, body.data.encode(), body.process_id)
    return {"ok": True}


@router.websocket("/{computer_id}/terminal/input")
async def terminal_socket(computer_id: UUID, websocket: WebSocket) -> None:
    # Authenticate in the first message: credentials never appear in the URL or access logs.
    await websocket.accept()
    try:
        origin = websocket.headers.get("origin", "")
        from urllib.parse import urlsplit
        if origin and (origin == "null" or urlsplit(origin).hostname != urlsplit("http://" + websocket.headers.get("host", "")).hostname):
            await websocket.close(code=1008)
            return
        hello = await asyncio.wait_for(websocket.receive_json(), 5)
        token = str(hello.get("token", ""))
        request = Request({"type": "http", "app": websocket.app, "headers": [(b"authorization", f"Bearer {token}".encode())]})
        context = await tenant_context(request)
        if ROLE_RANK[context.role] < ROLE_RANK["builder"] or (context.service_key and "write" not in context.scopes and "admin" not in context.scopes):
            await websocket.close(code=1008)
            return
        access, _ = await _computer_context(request, context, computer_id)
        await websocket.send_json({"ready": True})
        while True:
            body = TerminalInput.model_validate(await websocket.receive_json())
            current = await tenant_context(request)  # Recheck expiry, membership and role on every input.
            if ROLE_RANK[current.role] < ROLE_RANK["builder"] or (current.service_key and "write" not in current.scopes and "admin" not in current.scopes):
                await websocket.close(code=1008)
                return
            await websocket.app.state.services.interactive.input(access, computer_id, body.data.encode(), body.process_id)
            await websocket.send_json({"ok": True})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        return
    except Exception:
        await websocket.close(code=1008)


@router.post("/{computer_id}/terminal/control")
async def terminal_control(computer_id: UUID, body: ProcessControl, request: Request, context: BUILD) -> dict[str, object]:
    access, _ = await _computer_context(request, context, computer_id)
    return await get_services(request).interactive.control(access, computer_id, body.action, body.process_id)


@router.get("/{computer_id}/processes/{process_id}/logs")
async def process_logs(computer_id: UUID, process_id: str, request: Request, context: READ) -> dict[str, Any]:
    access, _ = await _computer_context(request, context, computer_id)
    return await get_services(request).interactive.logs(access, computer_id, process_id)


@router.post("/{computer_id}/restart")
async def restart_computer(computer_id: UUID, request: Request, context: BUILD) -> dict[str, bool]:
    access, _ = await _computer_context(request, context, computer_id)
    await get_services(request).interactive.restart(access, computer_id)
    return {"ok": True}


@router.post("/{computer_id}/snapshots/{snapshot_id}/restore")
async def restore_computer_files(computer_id: UUID, snapshot_id: str, request: Request, context: BUILD) -> dict[str, bool]:
    access, _ = await _computer_context(request, context, computer_id)
    await get_services(request).interactive.restore(access, computer_id, snapshot_id)
    return {"ok": True}


class BrowserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(mouse|key)$")
    type: str = Field(default="mousePressed", pattern=r"^(mousePressed|mouseReleased|mouseMoved|mouseWheel)$")
    x: float = Field(default=0, ge=0, le=1280)
    y: float = Field(default=0, ge=0, le=720)
    deltaX: float = Field(default=0, ge=-5000, le=5000)
    deltaY: float = Field(default=0, ge=-5000, le=5000)
    key: str = Field(default="", max_length=80)
    text: str = Field(default="", max_length=4096)
    modifiers: int = Field(default=0, ge=0, le=15)


@router.post("/{computer_id}/browser/input")
async def browser_input(computer_id: UUID, body: BrowserInput, request: Request, context: BUILD) -> dict[str, bool]:
    access, _ = await _computer_context(request, context, computer_id)
    await get_services(request).interactive.browser(access, computer_id, body.action, {**body.model_dump(exclude={"action"}), "human": True})
    return {"ok": True}
