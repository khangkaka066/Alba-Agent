"""Governed, tenant-scoped transfer of reusable agent learning."""

from .distiller import DistillationCandidate, DistillationTrigger, EpisodicKnowledgeDistiller
from .negative_transfer_detector import (
    DetectorConfig,
    TransferImpactScore,
    TransferObservation,
    TransferOutcome,
    TransferPairDecision,
    score_transfer_pair,
)
from .scope_firewall import (
    AgentLearningContext,
    FirewallDecision,
    LearningPolicy,
    ScopeFirewall,
    sanitize_capsule,
)

__all__ = [
    "AgentLearningContext", "DetectorConfig", "DistillationCandidate",
    "DistillationTrigger", "EpisodicKnowledgeDistiller", "FirewallDecision",
    "LearningPolicy", "ScopeFirewall", "TransferImpactScore",
    "TransferObservation", "TransferOutcome", "TransferPairDecision",
    "sanitize_capsule", "score_transfer_pair",
]
