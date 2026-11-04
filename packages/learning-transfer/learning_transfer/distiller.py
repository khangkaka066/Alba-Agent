"""Converts verified execution or human feedback into compact skill capsules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from nexus_core_schema.models import KnowledgeCapsuleSpec, PropagationScope, SensitivityLevel


MAX_PRECONDITIONS = 4000  # KnowledgeCapsuleSpec.trigger_preconditions
MAX_HEURISTIC = 8000  # KnowledgeCapsuleSpec.distilled_heuristic


class DistillationTrigger(StrEnum):
    DEBUG_RECOVERY = "debug_recovery"
    APPROVAL_CORRECTION = "approval_correction"
    HIGH_CONFIDENCE_TASK = "high_confidence_task"


@dataclass(frozen=True)
class DistillationCandidate:
    """Evidence gathered by a runtime hook; raw inputs are intentionally excluded."""

    tenant_id: UUID
    workspace_id: UUID
    source_agent_id: str
    source_role: str
    trigger: DistillationTrigger
    heuristic: str
    preconditions: str
    domain_tags: tuple[str, ...] = ()
    debug_turns: int = 0
    confidence: float = 0.0
    reviewer_feedback: str | None = None
    workflow_id: UUID | None = None
    crew_id: str | None = None
    propagation_scope: PropagationScope = PropagationScope.AGENT_PRIVATE


class EpisodicKnowledgeDistiller:
    """Distill only when a concrete success, correction, or confidence gate exists."""

    def __init__(self, high_confidence_threshold: float = 0.9) -> None:
        if not 0 < high_confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be between zero and one")
        self.high_confidence_threshold = high_confidence_threshold

    def distill(self, candidate: DistillationCandidate) -> KnowledgeCapsuleSpec | None:
        if candidate.trigger == DistillationTrigger.DEBUG_RECOVERY and candidate.debug_turns < 2:
            return None
        if candidate.trigger == DistillationTrigger.APPROVAL_CORRECTION and not (candidate.reviewer_feedback or "").strip():
            return None
        if candidate.trigger == DistillationTrigger.HIGH_CONFIDENCE_TASK and candidate.confidence < self.high_confidence_threshold:
            return None
        heuristic = (candidate.reviewer_feedback or "") if candidate.trigger == DistillationTrigger.APPROVAL_CORRECTION else candidate.heuristic
        if not heuristic.strip() or not candidate.preconditions.strip():
            return None
        return KnowledgeCapsuleSpec(
            tenant_id=candidate.tenant_id, workspace_id=candidate.workspace_id,
            capsule_id=uuid4(), source_agent_id=candidate.source_agent_id,
            source_role=candidate.source_role,
            source_domain_tags=tuple(dict.fromkeys(tag.strip().lower() for tag in candidate.domain_tags if tag.strip())),
            # A long request is text a capsule only needs the start of; the schema limits would otherwise fail a finished run.
            trigger_preconditions=candidate.preconditions.strip()[:MAX_PRECONDITIONS], distilled_heuristic=heuristic.strip()[:MAX_HEURISTIC],
            prohibited_contexts=(), propagation_scope=candidate.propagation_scope,
            sensitivity_level=SensitivityLevel.CONFIDENTIAL_PII_STRIPPED if candidate.trigger == DistillationTrigger.APPROVAL_CORRECTION else SensitivityLevel.INTERNAL,
            source_workflow_id=candidate.workflow_id, source_crew_id=candidate.crew_id,
            confidence=candidate.confidence if candidate.trigger == DistillationTrigger.HIGH_CONFIDENCE_TASK else 0.75,
        )
