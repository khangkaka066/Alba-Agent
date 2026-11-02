"""Task conversations: the chat thread of each task, saved so it can be reopened, and deleted together with its outputs."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import TenantContext, require_role
from app.models import AuditLog, ConversationMessage, TaskConversation, WorkflowRun
from app.models.scope import scoped_session
from app.routers.common import conflict, get_services, not_found
from nexus_core_schema.artifacts import artifact_directory

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]

TITLE_LIMIT = 200
TEXT_LIMIT = 4000


async def start_conversation(session: AsyncSession, context: TenantContext, title: str) -> TaskConversation:
    conversation = TaskConversation(id=uuid4(), tenant_id=context.tenant_id, workspace_id=context.workspace_id, title=(title.strip() or "Task")[:TITLE_LIMIT])
    session.add(conversation)
    await session.flush()
    return conversation


async def append_message(
    session: AsyncSession, conversation: TaskConversation, role: str, text: str, *,
    run_id: UUID | None = None, workflow_id: UUID | None = None, meta: dict[str, Any] | None = None,
) -> ConversationMessage:
    """Add the next message of a thread. The thread row is locked so concurrent writers get distinct sequence numbers."""
    await session.execute(select(TaskConversation.id).where(TaskConversation.id == conversation.id).with_for_update())
    last = await session.scalar(select(func.max(ConversationMessage.sequence)).where(ConversationMessage.conversation_id == conversation.id))
    message = ConversationMessage(
        id=uuid4(), tenant_id=conversation.tenant_id, workspace_id=conversation.workspace_id, conversation_id=conversation.id,
        sequence=(last or 0) + 1, role=role, text=text[:TEXT_LIMIT], run_id=run_id, workflow_id=workflow_id, meta=meta or {},
    )
    session.add(message)
    conversation.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return message


def _view(message: ConversationMessage) -> dict[str, Any]:
    return {
        "id": str(message.id), "sequence": message.sequence, "role": message.role, "text": message.text,
        "run_id": str(message.run_id) if message.run_id else None, "workflow_id": str(message.workflow_id) if message.workflow_id else None,
        "meta": message.meta, "created_at": message.created_at,
    }


class NoteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


@router.get("")
async def list_conversations(request: Request, context: READ) -> list[dict[str, Any]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(TaskConversation).order_by(TaskConversation.updated_at.desc()).limit(50))).all()
    return [{"id": str(row.id), "title": row.title, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: UUID, request: Request, context: READ) -> dict[str, Any]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        conversation = await session.get(TaskConversation, conversation_id)
        if conversation is None:
            raise not_found("Conversation is not visible in this workspace")
        messages = (await session.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id)
                                          .order_by(ConversationMessage.sequence))).all()
    return {"id": str(conversation.id), "title": conversation.title, "messages": [_view(message) for message in messages]}


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_note(conversation_id: UUID, body: NoteWrite, request: Request, context: BUILD) -> dict[str, Any]:
    """Only system notes come from the client; prompts and team cards are written by the server when a team is built."""
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        conversation = await session.get(TaskConversation, conversation_id)
        if conversation is None:
            raise not_found("Conversation is not visible in this workspace")
        return _view(await append_message(session, conversation, "note", body.text))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_conversation(conversation_id: UUID, request: Request, context: BUILD) -> Response:
    """Remove the thread, the runs it started (with their checkpoints and approvals) and their output files. The audit trail stays."""
    services = get_services(request)
    async with scoped_session(services.engine, context.tenant_id, context.workspace_id) as session:
        conversation = await session.get(TaskConversation, conversation_id)
        if conversation is None:
            raise not_found("Conversation is not visible in this workspace")
        run_ids = [run_id for run_id in (await session.scalars(select(ConversationMessage.run_id).where(
            ConversationMessage.conversation_id == conversation_id, ConversationMessage.run_id.is_not(None)).distinct())).all() if run_id is not None]
        runs = (await session.scalars(select(WorkflowRun).where(WorkflowRun.id.in_(run_ids)))).all() if run_ids else []
        if any(run.status in ("queued", "running") for run in runs):
            raise conflict("A task that is still running cannot be deleted")
        for run in runs:
            await session.delete(run)
        await session.delete(conversation)
        session.add(AuditLog(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id, actor_id=context.user_id, action="conversation.deleted",
            target_type="conversation", target_id=conversation_id, details={"runs": len(runs)},
        ))
    for run_id in run_ids:
        shutil.rmtree(artifact_directory(context.tenant_id, context.workspace_id, run_id), ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
