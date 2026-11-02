"""Scoped persistence helpers for distilled learning capsules."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING
from uuid import uuid4

from qdrant_client import models as qmodels
from sqlalchemy import select

from app.models import KnowledgeCapsule
from app.models.scope import scoped_session
from nexus_core_schema.models import KnowledgeCapsuleSpec
from learning_transfer.scope_firewall import sanitize_capsule

if TYPE_CHECKING:
    from app.services import AppServices


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def vectorize_capsule(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9_+#.-]+", text.casefold()):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        vector[value % dimensions] += 1.0 if value & 1 else -1.0
    norm = sum(component * component for component in vector) ** 0.5
    return [component / norm for component in vector] if norm else vector


async def save_capsule(services: AppServices, capsule: KnowledgeCapsuleSpec) -> None:
    capsule = sanitize_capsule(capsule)
    async with scoped_session(services.engine, capsule.tenant_id, capsule.workspace_id) as session:
        existing = await session.scalar(select(KnowledgeCapsule).where(KnowledgeCapsule.capsule_id == capsule.capsule_id))
        if existing is None:
            session.add(KnowledgeCapsule(
                id=uuid4(), capsule_id=capsule.capsule_id, tenant_id=capsule.tenant_id,
                workspace_id=capsule.workspace_id, source_agent_id=capsule.source_agent_id,
                source_role=capsule.source_role, source_domain_tags=list(capsule.source_domain_tags),
                trigger_preconditions=capsule.trigger_preconditions, distilled_heuristic=capsule.distilled_heuristic,
                prohibited_contexts=list(capsule.prohibited_contexts), propagation_scope=_value(capsule.propagation_scope),
                sensitivity_level=_value(capsule.sensitivity_level), source_workflow_id=capsule.source_workflow_id,
                source_crew_id=capsule.source_crew_id, confidence=capsule.confidence,
                status="active", vector_id=str(capsule.capsule_id),
            ))
    collection = "knowledge_capsules"
    collections = await services.qdrant.get_collections()
    if not any(item.name == collection for item in collections.collections):
        await services.qdrant.create_collection(collection_name=collection,
            vectors_config=qmodels.VectorParams(size=64, distance=qmodels.Distance.COSINE))
        await services.qdrant.create_payload_index(collection, "tenant_id", qmodels.PayloadSchemaType.KEYWORD)
        await services.qdrant.create_payload_index(collection, "workspace_id", qmodels.PayloadSchemaType.KEYWORD)
    searchable = " ".join((capsule.source_role, *capsule.source_domain_tags,
                           capsule.trigger_preconditions, capsule.distilled_heuristic))
    await services.qdrant.upsert(collection_name=collection, points=[qmodels.PointStruct(
        id=str(capsule.capsule_id), vector=vectorize_capsule(searchable), payload={
            "tenant_id": str(capsule.tenant_id), "workspace_id": str(capsule.workspace_id),
            "capsule_id": str(capsule.capsule_id), "source_agent_id": capsule.source_agent_id,
            "source_domain_tags": list(capsule.source_domain_tags),
            "propagation_scope": _value(capsule.propagation_scope),
            "sensitivity_level": _value(capsule.sensitivity_level),
        },
    )])
