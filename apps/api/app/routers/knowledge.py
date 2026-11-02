"""Knowledge base administration, bounded document upload, and retrieval tests."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth.context import TenantContext, require_role
from app.billing.plans import tenant_plan
from app.models import KnowledgeBase, KnowledgeDocument
from app.models.scope import scoped_session
from app.routers.common import get_services, not_found
from nexus_rag_engine import KnowledgeScope

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge"])
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]


class KnowledgeBaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    embedding_model: str = Field(min_length=3, max_length=200, pattern=r"^[a-z0-9_]+/.+$")
    id: UUID | None = None


class KnowledgeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=100_000)
    limit: int = Field(default=5, ge=1, le=100)


@router.get("")
async def list_knowledge_bases(request: Request, context: READ) -> list[dict[str, str]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        rows = (await session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.name))).all()
        return [{"id": str(row.id), "name": row.name, "embedding_model": row.embedding_model} for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(body: KnowledgeBaseRequest, request: Request, context: BUILD) -> dict[str, str]:
    identifier = body.id or uuid4()
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        session.add(KnowledgeBase(
            id=identifier, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            name=body.name, embedding_model=body.embedding_model,
        ))
    return {"id": str(identifier), "name": body.name, "embedding_model": body.embedding_model}


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_knowledge_base(knowledge_base_id: UUID, request: Request, context: BUILD) -> Response:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.get(KnowledgeBase, knowledge_base_id)
        if row is None:
            raise not_found("Knowledge base is not visible in this workspace")
        await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{knowledge_base_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(knowledge_base_id: UUID, request: Request, filename: str, context: BUILD) -> dict[str, str]:
    if len(filename) > 500:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Document filename is too long")
    content = await request.body()
    if not content or len(content) > 20 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Document must be between 1 byte and 20 MiB")
    services = get_services(request)
    _, plan_limits = await tenant_plan(services.engine, context.tenant_id, context.workspace_id)
    try:
        document_id = await services.rag().ingest(
            KnowledgeScope(context.tenant_id, context.workspace_id, knowledge_base_id), filename, content,
            max_chunks=plan_limits.max_vector_chunks,
        )
    except LookupError as error:
        raise not_found("Knowledge base is not visible in this workspace") from error
    except (ValueError, OSError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return {"document_id": str(document_id), "filename": filename, "status": "ready"}


@router.get("/{knowledge_base_id}/documents")
async def list_documents(knowledge_base_id: UUID, request: Request, context: READ) -> list[dict[str, str]]:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        if await session.get(KnowledgeBase, knowledge_base_id) is None:
            raise not_found("Knowledge base is not visible in this workspace")
        rows = (await session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == knowledge_base_id).order_by(KnowledgeDocument.created_at.desc()))).all()
        return [{"id": str(row.id), "filename": row.filename, "status": row.status, "content_sha256": row.content_sha256} for row in rows]


@router.post("/{knowledge_base_id}/query")
async def query_knowledge(knowledge_base_id: UUID, body: KnowledgeQuery, request: Request, context: READ) -> list[dict[str, Any]]:
    try:
        hits = await get_services(request).rag().retrieve(
            KnowledgeScope(context.tenant_id, context.workspace_id, knowledge_base_id), body.query, limit=body.limit,
        )
    except LookupError as error:
        raise not_found("Knowledge base is not visible in this workspace") from error
    return [{"document_id": str(hit.document_id), "filename": hit.filename, "text": hit.text, "score": hit.score, "chunk_index": hit.chunk_index} for hit in hits]
