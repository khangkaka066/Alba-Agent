"""Lifecycle hooks for artifact contracts, path-scoped standards and visual QA evidence."""

from .validator import (
    DEFAULT_PATH_RULES,
    ArtifactCheck,
    ArtifactContractHook,
    ArtifactContractReport,
    GateVerdict,
    LifecycleHookEngine,
    PathScopedRuleInjector,
    VisualEvidenceHook,
    VisualEvidenceReport,
)

__all__ = [
    "DEFAULT_PATH_RULES", "ArtifactCheck", "ArtifactContractHook", "ArtifactContractReport", "GateVerdict",
    "LifecycleHookEngine", "PathScopedRuleInjector", "VisualEvidenceHook", "VisualEvidenceReport",
]
