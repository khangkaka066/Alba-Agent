"""Export deterministic JSON Schemas for TypeScript consumers."""

from __future__ import annotations

import json
from pathlib import Path

from nexus_core_schema import (
    AgentSpec,
    ApprovalGateNodeSpec,
    ApprovalRequestSpec,
    NexusGenSandboxNodeSpec,
    CrewNodeSpec,
    MarkdownRoutineSpec,
    KnowledgeCapsuleSpec,
    LearningEdgeSpec,
    LearningMetricSample,
    NodePosition,
    PersistentBotSpec,
    RAGNodeSpec,
    RouterNodeSpec,
    RuntimeEvent,
    SandboxComputerSpec,
    TaskSpec,
    TransferTelemetrySpec,
    WorkflowEdgeSpec,
    WorkflowModesSpec,
    PathRuleSpec,
    WorkflowSpec,
    TemplateCatalogEntry,
    TemplateInstantiationRequest,
    TemplateInstantiationResponse,
    BUILTIN_OUTPUT_SCHEMAS,
)

MODELS = (
    NodePosition,
    WorkflowSpec,
    CrewNodeSpec,
    AgentSpec,
    TaskSpec,
    NexusGenSandboxNodeSpec,
    ApprovalGateNodeSpec,
    WorkflowEdgeSpec,
    WorkflowModesSpec,
    PathRuleSpec,
    RouterNodeSpec,
    RAGNodeSpec,
    PersistentBotSpec,
    MarkdownRoutineSpec,
    ApprovalRequestSpec,
    SandboxComputerSpec,
    RuntimeEvent,
    KnowledgeCapsuleSpec,
    LearningEdgeSpec,
    LearningMetricSample,
    TransferTelemetrySpec,
    TemplateCatalogEntry,
    TemplateInstantiationRequest,
    TemplateInstantiationResponse,
) + tuple(BUILTIN_OUTPUT_SCHEMAS.values())


def export(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        path = output_dir / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export(Path(__file__).resolve().parents[1] / "typescript" / "schemas")
