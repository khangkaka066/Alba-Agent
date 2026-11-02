"""Sentence-aware ingestion and filtered dense/sparse Qdrant retrieval."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import math
import os
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import cast
from uuid import UUID, NAMESPACE_URL, uuid5

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

from docx import Document as DocxDocument
from llama_index.core.node_parser import SentenceSplitter
from pypdf import PdfReader
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import KnowledgeBase, KnowledgeDocument
from app.models.scope import scoped_session
from nexus_model_gateway import EmbeddingRequest, LiteLLMEmbeddingRouter
from nexus_model_gateway.router import BillingMode, Provider

TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class KnowledgeScope:
    tenant_id: UUID
    workspace_id: UUID
    knowledge_base_id: UUID


@dataclass(frozen=True)
class EmbeddingAccess:
    billing_mode: BillingMode = "platform"
    credential_id: UUID | None = None
    api_base: str | None = None
    max_input_tokens: int = 8192


@dataclass(frozen=True)
class RetrievalHit:
    document_id: UUID
    filename: str
    text: str
    score: float
    chunk_index: int


def _parse_document(filename: str, content: bytes) -> str:
    if not filename or PurePath(filename).name != filename or not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Document name or size is invalid")
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        document = DocxDocument(io.BytesIO(content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        for table in document.tables:
            text += "\n" + "\n".join(" | ".join(cell.text for cell in row.cells) for row in table.rows)
    elif suffix in (".md", ".markdown"):
        text = content.decode("utf-8-sig")
    elif suffix == ".csv":
        csv_reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if not csv_reader.fieldnames:
            raise ValueError("CSV document has no header")
        text = "\n".join(
            "; ".join(f"{key}: {value or ''}" for key, value in row.items() if key is not None)
            for row in csv_reader
        )
    else:
        raise ValueError("Document type must be PDF, DOCX, Markdown, or CSV")
    if not text.strip():
        raise ValueError("Document contains no extractable text")
    return text.strip()


def _sparse_vector(text: str) -> models.SparseVector:
    counts: dict[int, int] = {}
    for token in TOKEN_PATTERN.findall(text.casefold()):
        index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
        counts[index] = counts.get(index, 0) + 1
    if not counts:
        raise ValueError("Knowledge text has no searchable tokens")
    total = sum(counts.values())
    indices = sorted(counts)
    return models.SparseVector(indices=indices, values=[counts[index] / total for index in indices])


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


class MultiTenantRAGEngine:
    def __init__(
        self,
        engine: AsyncEngine,
        qdrant: AsyncQdrantClient,
        embeddings: LiteLLMEmbeddingRouter,
        chunk_size: int = 384,
        similarity_threshold: float = 0.72,
    ) -> None:
        if chunk_size < 64 or not -1 <= similarity_threshold <= 1:
            raise ValueError("Chunk size or similarity threshold is invalid")
        self._engine = engine
        self._qdrant = qdrant
        self._embeddings = embeddings
        self._splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=0)
        self._similarity_threshold = similarity_threshold

    async def _model(self, scope: KnowledgeScope) -> tuple[Provider, str]:
        async with scoped_session(self._engine, scope.tenant_id, scope.workspace_id) as session:
            row = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.id == scope.knowledge_base_id))
            if row is None:
                raise LookupError("Knowledge base is not visible in this workspace")
            provider_name, separator, model = row.embedding_model.partition("/")
        if not separator or provider_name not in ("openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm") or not model:
            raise ValueError("Knowledge base lacks an approved embedding provider/model")
        return cast(Provider, provider_name), model

    @staticmethod
    def _collection(provider: Provider, model: str, dimension: int) -> str:
        digest = hashlib.sha256(f"{provider}/{model}".encode()).hexdigest()[:16]
        return f"nexus_knowledge_{digest}_{dimension}"

    @staticmethod
    def scope_filter(scope: KnowledgeScope, document_id: UUID | None = None) -> models.Filter:
        conditions: list[models.Condition] = [
            models.FieldCondition(key="tenant_id", match=models.MatchValue(value=str(scope.tenant_id))),
            models.FieldCondition(key="workspace_id", match=models.MatchValue(value=str(scope.workspace_id))),
            models.FieldCondition(key="knowledge_base_id", match=models.MatchValue(value=str(scope.knowledge_base_id))),
        ]
        if document_id is not None:
            conditions.append(models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_id))))
        return models.Filter(must=conditions)

    async def _embed(
        self, scope: KnowledgeScope, provider: Provider, model: str,
        texts: tuple[str, ...], access: EmbeddingAccess,
    ) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for offset in range(0, len(texts), 8):
            batch = texts[offset:offset + 8]
            result = await self._embeddings.embed(EmbeddingRequest(
                tenant_id=scope.tenant_id, workspace_id=scope.workspace_id,
                provider=provider, model=model, texts=batch,
                max_input_tokens=access.max_input_tokens,
                billing_mode=access.billing_mode,
                credential_id=access.credential_id, api_base=access.api_base,
            ))
            vectors.extend(result.vectors)
        return tuple(vectors)

    async def _semantic_chunks(
        self, scope: KnowledgeScope, provider: Provider, model: str,
        text: str, access: EmbeddingAccess,
    ) -> tuple[str, ...]:
        candidates = tuple(part.strip() for part in self._splitter.split_text(text) if part.strip())
        if not candidates:
            raise ValueError("Document has no searchable chunks")
        if len(candidates) == 1:
            return candidates
        vectors = await self._embed(scope, provider, model, candidates, access)
        groups: list[str] = []
        current = candidates[0]
        for index in range(1, len(candidates)):
            if _cosine(vectors[index - 1], vectors[index]) < self._similarity_threshold:
                groups.append(current)
                current = candidates[index]
            else:
                current += "\n" + candidates[index]
        groups.append(current)
        return tuple(groups)

    async def _ensure_collection(self, name: str, dimension: int) -> None:
        if await self._qdrant.collection_exists(name):
            return
        try:
            await self._qdrant.create_collection(
                collection_name=name,
                vectors_config={"dense": models.VectorParams(size=dimension, distance=models.Distance.COSINE)},
                sparse_vectors_config={"lexical": models.SparseVectorParams()},
            )
        except Exception:
            if not await self._qdrant.collection_exists(name):
                raise
        for field in ("tenant_id", "workspace_id", "knowledge_base_id", "document_id"):
            await self._qdrant.create_payload_index(
                collection_name=name, field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD, wait=True,
            )

    async def ingest(
        self, scope: KnowledgeScope, filename: str, content: bytes,
        access: EmbeddingAccess = EmbeddingAccess(), max_chunks: int | None = None,
    ) -> UUID:
        provider, model = await self._model(scope)
        text = _parse_document(filename, content)
        chunks = await self._semantic_chunks(scope, provider, model, text, access)
        vectors = await self._embed(scope, provider, model, chunks, access)
        dimension = len(vectors[0])
        collection = self._collection(provider, model, dimension)
        if max_chunks is not None:
            if max_chunks < 0:
                raise ValueError("Chunk quota cannot be negative")
            tenant_filter = models.Filter(must=[models.FieldCondition(
                key="tenant_id", match=models.MatchValue(value=str(scope.tenant_id)),
            )])
            collections = await self._qdrant.get_collections()
            counts = await asyncio.gather(*(
                self._qdrant.count(collection_name=item.name, count_filter=tenant_filter, exact=True)
                for item in collections.collections
            ))
            if sum(item.count for item in counts) + len(chunks) > max_chunks:
                raise ValueError("Tenant plan vector chunk limit reached")
        document = KnowledgeDocument(
            tenant_id=scope.tenant_id, workspace_id=scope.workspace_id,
            knowledge_base_id=scope.knowledge_base_id, filename=filename,
            content_sha256=hashlib.sha256(content).hexdigest(), status="processing",
        )
        async with scoped_session(self._engine, scope.tenant_id, scope.workspace_id) as session:
            session.add(document)
            await session.flush()
            document_id = document.id
        try:
            await self._ensure_collection(collection, dimension)
            points = [
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"{document_id}:{index}")),
                    vector={"dense": list(vector), "lexical": _sparse_vector(chunk)},
                    payload={
                        "tenant_id": str(scope.tenant_id),
                        "workspace_id": str(scope.workspace_id),
                        "knowledge_base_id": str(scope.knowledge_base_id),
                        "document_id": str(document_id),
                        "filename": filename, "text": chunk, "chunk_index": index,
                    },
                )
                for index, (chunk, vector) in enumerate(zip(chunks, vectors))
            ]
            await self._qdrant.upsert(collection_name=collection, points=points, wait=True)
        except Exception:
            if await self._qdrant.collection_exists(collection):
                await self._qdrant.delete(
                    collection_name=collection,
                    points_selector=models.FilterSelector(filter=self.scope_filter(scope, document_id)),
                    wait=True,
                )
            async with scoped_session(self._engine, scope.tenant_id, scope.workspace_id) as session:
                row = await session.get(KnowledgeDocument, document_id)
                if row is not None:
                    row.status = "failed"
            raise
        async with scoped_session(self._engine, scope.tenant_id, scope.workspace_id) as session:
            row = await session.get(KnowledgeDocument, document_id)
            if row is None:
                raise LookupError("Ingested document disappeared")
            row.status = "ready"
        return document_id

    async def retrieve(
        self, scope: KnowledgeScope, query: str, access: EmbeddingAccess = EmbeddingAccess(), limit: int = 5,
    ) -> tuple[RetrievalHit, ...]:
        if not query.strip() or not 1 <= limit <= 100:
            raise ValueError("Knowledge query or limit is invalid")
        provider, model = await self._model(scope)
        vector = (await self._embed(scope, provider, model, (query,), access))[0]
        collection = self._collection(provider, model, len(vector))
        if not await self._qdrant.collection_exists(collection):
            return ()
        scope_filter = self.scope_filter(scope)
        response = await self._qdrant.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(query=list(vector), using="dense", filter=scope_filter, limit=max(limit * 4, 20)),
                models.Prefetch(query=_sparse_vector(query), using="lexical", filter=scope_filter, limit=max(limit * 4, 20)),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=scope_filter,
            limit=limit,
            with_payload=True,
        )
        hits: list[RetrievalHit] = []
        for point in response.points:
            payload = point.payload or {}
            if (payload.get("tenant_id"), payload.get("workspace_id"), payload.get("knowledge_base_id")) != (
                str(scope.tenant_id), str(scope.workspace_id), str(scope.knowledge_base_id)
            ):
                raise RuntimeError("Qdrant returned a point outside the mandatory scope")
            hits.append(RetrievalHit(
                document_id=UUID(str(payload["document_id"])),
                filename=str(payload["filename"]),
                text=str(payload["text"]),
                score=float(point.score),
                chunk_index=int(payload["chunk_index"]),
            ))
        return tuple(hits)
