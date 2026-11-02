"""Persistent bot, conversation, voice, and Markdown routine APIs."""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import json
import os
from typing import Annotated, Any, Awaitable, Literal, cast
from urllib.parse import quote
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.context import TenantContext, _membership, decode_voice_token, issue_voice_token, require_role
from app.billing.plans import enforce_creation_quota
from app.models import BotMessage, BotRoutine, PersistentBot, RoutineRun, Workflow
from app.models.scope import scoped_session
from app.routers.common import conflict, get_services, not_found
from bots.runner import cron_matches
from nexus_core_schema.models import MarkdownRoutineSpec, PersistentBotSpec
from nexus_core_schema.artifacts import MEDIA_TYPES, artifact_directory, artifact_file, list_artifacts

router = APIRouter(tags=["teammates"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]
RUN = Annotated[TenantContext, Depends(require_role("builder", "run"))]


class BotTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=100_000)
    thread_id: UUID | None = None


class BotTurnResponse(BaseModel):
    thread_id: UUID
    status: Literal["queued"] = "queued"


class VoiceTokenResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 300


class RoutineRunResponse(BaseModel):
    run_id: UUID
    routine_id: UUID
    status: str


def _bot_spec(spec: PersistentBotSpec, context: TenantContext) -> None:
    if (spec.tenant_id, spec.workspace_id) != (context.tenant_id, context.workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bot scope does not match authenticated workspace")


def _routine_spec(spec: MarkdownRoutineSpec, context: TenantContext) -> None:
    if (spec.tenant_id, spec.workspace_id) != (context.tenant_id, context.workspace_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Routine scope does not match authenticated workspace")
    if spec.interval_seconds is None:
        try:
            cron_matches(spec.cron_expression, datetime.now(timezone.utc), spec.timezone)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine cron or timezone is invalid") from error
    try:
        ZoneInfo(spec.timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine timezone is invalid") from error


async def _register_scope(request: Request, context: TenantContext) -> None:
    services = get_services(request)
    result = cast(Awaitable[int], services.redis.sadd(f"nexus:{context.tenant_id}:scheduler:workspaces", str(context.workspace_id)))
    await result


@router.get("/api/v1/bots", response_model=list[PersistentBotSpec])
async def list_bots(request: Request, context: READ) -> list[PersistentBotSpec]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(PersistentBot).order_by(PersistentBot.name))).all()
        return [PersistentBotSpec.model_validate(row.spec) for row in rows]


@router.post("/api/v1/bots", response_model=PersistentBotSpec, status_code=status.HTTP_201_CREATED)
async def create_bot(spec: PersistentBotSpec, request: Request, context: BUILD) -> PersistentBotSpec:
    _bot_spec(spec, context)
    await enforce_creation_quota(get_services(request).engine, context.tenant_id, context.workspace_id, "bot")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        session.add(PersistentBot(
            id=spec.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            name=spec.name, model=spec.model, spec=spec.model_dump(mode="json"),
        ))
    return spec


@router.get("/api/v1/bots/{bot_id}", response_model=PersistentBotSpec)
async def get_bot(bot_id: UUID, request: Request, context: READ) -> PersistentBotSpec:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(PersistentBot, bot_id)
        if row is None:
            raise not_found("Bot is not visible in this workspace")
        return PersistentBotSpec.model_validate(row.spec)


@router.put("/api/v1/bots/{bot_id}", response_model=PersistentBotSpec)
async def update_bot(bot_id: UUID, spec: PersistentBotSpec, request: Request, context: BUILD) -> PersistentBotSpec:
    _bot_spec(spec, context)
    if spec.id != bot_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bot ID cannot change")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(PersistentBot).where(PersistentBot.id == bot_id).with_for_update())
        if row is None:
            raise not_found("Bot is not visible in this workspace")
        row.name, row.model, row.spec = spec.name, spec.model, spec.model_dump(mode="json")
    return spec


@router.delete("/api/v1/bots/{bot_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_bot(bot_id: UUID, request: Request, context: BUILD) -> Response:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(PersistentBot, bot_id)
        if row is None:
            raise not_found("Bot is not visible in this workspace")
        await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/bots/{bot_id}/turns", response_model=BotTurnResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_bot_turn(bot_id: UUID, body: BotTurnRequest, request: Request, context: RUN) -> BotTurnResponse:
    thread_id = body.thread_id or uuid4()
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(PersistentBot, bot_id) is None:
            raise not_found("Bot is not visible in this workspace")
    try:
        await services.dispatcher.bot_turn(context.tenant_id, context.workspace_id, bot_id, thread_id, body.content)
    except Exception as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bot worker queue is unavailable") from error
    return BotTurnResponse(thread_id=thread_id)


@router.get("/api/v1/bots/{bot_id}/threads/{thread_id}")
async def get_bot_thread(bot_id: UUID, thread_id: UUID, request: Request, context: READ) -> list[dict[str, str]]:
    try:
        history = await get_services(request).bot_runner(context.tenant_id, context.workspace_id, context.user_id).history(bot_id, thread_id)
    except LookupError as error:
        raise not_found("Bot thread is not visible in this workspace") from error
    return [{"role": role, "content": content} for role, content in history]


@router.get("/api/v1/bots/{bot_id}/artifacts")
async def bot_artifacts(bot_id: UUID, request: Request, context: READ) -> list[dict[str, Any]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(PersistentBot, bot_id) is None:
            raise not_found("Bot is not visible in this workspace")
    return [{**item, "download_url": f"/api/v1/bots/{bot_id}/artifacts/{quote(item['filename'], safe='/')}",
             "preview_url": f"/api/v1/bots/{bot_id}/artifacts/{quote(item['filename'], safe='/')}"}
            for item in list_artifacts(context.tenant_id, context.workspace_id, bot_id)]


@router.get("/api/v1/bots/{bot_id}/artifacts/{filename:path}")
async def download_bot_artifact(bot_id: UUID, filename: str, request: Request, context: READ) -> FileResponse:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(PersistentBot, bot_id) is None:
            raise not_found("Bot is not visible in this workspace")
    try:
        path = artifact_file(artifact_directory(context.tenant_id, context.workspace_id, bot_id), filename)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    if not path.is_file():
        raise not_found("Artifact is unavailable")
    mime_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=mime_type, filename=path.name,
        content_disposition_type="inline" if mime_type.startswith(("image/", "audio/", "video/")) else "attachment")


@router.post("/api/v1/bots/{bot_id}/voice-session", response_model=VoiceTokenResponse)
async def create_voice_session(bot_id: UUID, request: Request, context: RUN) -> VoiceTokenResponse:
    if context.service_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Voice sessions require a user access token")
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(PersistentBot, bot_id) is None:
            raise not_found("Bot is not visible in this workspace")
    return VoiceTokenResponse(token=issue_voice_token(context, bot_id))


@router.websocket("/api/v1/bots/{bot_id}/voice/stream")
async def voice_stream(websocket: WebSocket, bot_id: UUID) -> None:
    token = websocket.query_params.get("token", "")
    try:
        tenant_id, workspace_id, user_id = decode_voice_token(token, bot_id)
        services = websocket.app.state.services
        await _membership(services.engine, tenant_id, workspace_id, user_id)
        async with scoped_session(services.engine, tenant_id, workspace_id) as session:
            if await session.get(PersistentBot, bot_id) is None:
                raise LookupError("Bot is not visible in this workspace")
    except (ValueError, LookupError, HTTPException):
        await websocket.close(code=4401, reason="Voice session is invalid or expired")
        return

    await websocket.accept()
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                return
            if message.get("bytes") is not None:
                chunk = cast(bytes, message["bytes"])
                total_bytes += len(chunk)
                if total_bytes > 25 * 1024 * 1024:
                    await websocket.send_json({"type": "error", "text": "Audio turn exceeds the 25 MiB limit"})
                    chunks.clear()
                    total_bytes = 0
                    continue
                chunks.append(chunk)
                continue
            try:
                command = json.loads(cast(str, message.get("text") or "{}"))
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "text": "Voice control message is invalid"})
                continue
            if command.get("type") != "end_turn":
                continue
            audio = b"".join(chunks)
            chunks.clear()
            total_bytes = 0
            if len(audio) < 256:
                await websocket.send_json({"type": "error", "text": "Speak before ending the voice turn"})
                continue

            stt_key = os.environ.get("NEXUS_STT_API_KEY") or os.environ.get("NEXUS_OPENAI_API_KEY")
            if not stt_key:
                await websocket.send_json({"type": "error", "text": "Voice transcription needs NEXUS_STT_API_KEY or NEXUS_OPENAI_API_KEY"})
                continue
            stt_base = os.environ.get("NEXUS_STT_API_BASE", "https://api.openai.com/v1").rstrip("/")
            content_type = str(command.get("content_type", "audio/webm"))
            suffix = "wav" if "wav" in content_type else "webm"
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
                response = await client.post(
                    f"{stt_base}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {stt_key}"},
                    data={"model": os.environ.get("NEXUS_STT_MODEL", "whisper-1")},
                    files={"file": (f"utterance.{suffix}", audio, content_type)},
                )
                response.raise_for_status()
                transcript = response.json().get("text")
            if not isinstance(transcript, str) or not transcript.strip():
                await websocket.send_json({"type": "error", "text": "Speech transcription returned no words"})
                continue
            await websocket.send_json({"type": "transcript", "text": transcript})
            thread_id = UUID(str(command["thread_id"])) if command.get("thread_id") else uuid4()
            answer = await services.bot_runner(tenant_id, workspace_id, user_id).chat(bot_id, thread_id, transcript)
            tts_key = os.environ.get("NEXUS_TTS_API_KEY") or os.environ.get("NEXUS_OPENAI_API_KEY")
            await websocket.send_json({"type": "response", "text": answer, "audio_expected": bool(tts_key)})
            if tts_key:
                tts_base = os.environ.get("NEXUS_TTS_API_BASE", "https://api.openai.com/v1").rstrip("/")
                async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
                    async with client.stream(
                        "POST", f"{tts_base}/audio/speech",
                        headers={"Authorization": f"Bearer {tts_key}"},
                        json={"model": os.environ.get("NEXUS_TTS_MODEL", "tts-1"), "voice": os.environ.get("NEXUS_TTS_VOICE", "alloy"), "input": answer, "response_format": "mp3"},
                    ) as response:
                        response.raise_for_status()
                        sequence = 0
                        async for part in response.aiter_bytes(48 * 1024):
                            if part:
                                await websocket.send_json({
                                    "type": "audio_chunk", "sequence": sequence,
                                    "content_type": "audio/mpeg",
                                    "audio_base64": base64.b64encode(part).decode("ascii"),
                                })
                                sequence += 1
                await websocket.send_json({"type": "audio_complete"})
    except WebSocketDisconnect:
        return
    except (httpx.HTTPError, ValueError, RuntimeError, LookupError) as error:
        try:
            await websocket.send_json({"type": "error", "text": f"Voice turn failed: {type(error).__name__}"})
        except RuntimeError:
            return


@router.get("/api/v1/routines", response_model=list[MarkdownRoutineSpec])
async def list_routines(request: Request, context: READ) -> list[MarkdownRoutineSpec]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(BotRoutine).order_by(BotRoutine.name))).all()
        return [MarkdownRoutineSpec(
            id=row.id, tenant_id=row.tenant_id, workspace_id=row.workspace_id,
            bot_id=row.bot_id, name=row.name, instruction_markdown=row.instruction_markdown,
            cron_expression=row.cron_expression, timezone=row.timezone, enabled=row.enabled,
            workflow_id=row.workflow_id, interval_seconds=row.interval_seconds,
        ) for row in rows]


@router.post("/api/v1/routines", response_model=MarkdownRoutineSpec, status_code=status.HTTP_201_CREATED)
async def create_routine(spec: MarkdownRoutineSpec, request: Request, context: BUILD) -> MarkdownRoutineSpec:
    _routine_spec(spec, context)
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(PersistentBot, spec.bot_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine bot is not in this workspace")
        if spec.workflow_id is not None and await session.get(Workflow, spec.workflow_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine workflow is not in this workspace")
        session.add(BotRoutine(
            id=spec.id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            bot_id=spec.bot_id, name=spec.name, instruction_markdown=spec.instruction_markdown,
            cron_expression=spec.cron_expression, timezone=spec.timezone, enabled=spec.enabled,
            workflow_id=spec.workflow_id, interval_seconds=spec.interval_seconds,
        ))
    await _register_scope(request, context)
    return spec


@router.put("/api/v1/routines/{routine_id}", response_model=MarkdownRoutineSpec)
async def update_routine(routine_id: UUID, spec: MarkdownRoutineSpec, request: Request, context: BUILD) -> MarkdownRoutineSpec:
    _routine_spec(spec, context)
    if spec.id != routine_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine ID cannot change")
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(BotRoutine).where(BotRoutine.id == routine_id).with_for_update())
        if row is None:
            raise not_found("Routine is not visible in this workspace")
        if await session.get(PersistentBot, spec.bot_id) is None or (spec.workflow_id and await session.get(Workflow, spec.workflow_id) is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Routine bot or workflow is not in this workspace")
        row.bot_id, row.name, row.instruction_markdown = spec.bot_id, spec.name, spec.instruction_markdown
        row.cron_expression, row.timezone, row.enabled = spec.cron_expression, spec.timezone, spec.enabled
        row.workflow_id, row.interval_seconds = spec.workflow_id, spec.interval_seconds
    await _register_scope(request, context)
    return spec


@router.delete("/api/v1/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_routine(routine_id: UUID, request: Request, context: BUILD) -> Response:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(BotRoutine, routine_id)
        if row is None:
            raise not_found("Routine is not visible in this workspace")
        await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/routines/{routine_id}/runs", response_model=RoutineRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_routine(routine_id: UUID, request: Request, context: RUN) -> RoutineRunResponse:
    services = get_services(request)
    run_id = uuid4()
    now = datetime.now(timezone.utc)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        routine = await session.get(BotRoutine, routine_id)
        if routine is None or not routine.enabled:
            raise not_found("Enabled routine is not visible in this workspace")
        session.add(RoutineRun(
            id=run_id, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            bot_id=routine.bot_id, routine_id=routine_id, scheduled_for=now,
            status="queued", checkpoint={"stage": "queued"},
        ))
    try:
        await services.dispatcher.routine(context.tenant_id, context.workspace_id, run_id)
    except Exception as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Routine worker queue is unavailable") from error
    return RoutineRunResponse(run_id=run_id, routine_id=routine_id, status="queued")
