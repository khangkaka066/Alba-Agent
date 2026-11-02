from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from learning_transfer.distiller import DistillationCandidate, DistillationTrigger, EpisodicKnowledgeDistiller
from learning_transfer.negative_transfer_detector import DetectorConfig, TransferObservation, score_transfer_pair
from learning_transfer.scope_firewall import AgentLearningContext, LearningPolicy, ScopeFirewall, sanitize_capsule
from nexus_core_schema.models import (
    AgentSpec,
    CrewNodeSpec,
    KnowledgeCapsuleSpec,
    LearningEdgeSpec,
    PropagationScope,
    SensitivityLevel,
    StartNodeSpec,
    TaskSpec,
    WorkflowSpec,
    WorkflowEdgeSpec,
)
from app.main import create_app


def _capsule(tenant_id: UUID, workspace_id: UUID) -> KnowledgeCapsuleSpec:
    return KnowledgeCapsuleSpec(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        capsule_id=uuid4(),
        source_agent_id="data_coder",
        source_role="Data Engineer",
        source_domain_tags=("python", "pandas", "csv-encoding"),
        trigger_preconditions="Use when parsing CSV files that may contain byte order marks.",
        distilled_heuristic="Open CSV input with encoding utf-8-sig before parsing.",
        propagation_scope=PropagationScope.CREW_LOCAL,
        sensitivity_level=SensitivityLevel.INTERNAL,
        source_crew_id="data_crew",
        confidence=0.95,
    )


def test_distiller_requires_two_recovery_turns_and_serializes_capsule() -> None:
    tenant_id, workspace_id = uuid4(), uuid4()
    distiller = EpisodicKnowledgeDistiller()
    candidate = DistillationCandidate(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        source_agent_id="data_coder",
        source_role="Data Engineer",
        trigger=DistillationTrigger.DEBUG_RECOVERY,
        heuristic="Decode with utf-8-sig to strip a CSV BOM.",
        preconditions="CSV parsing fails on a byte order mark.",
        domain_tags=("Python", "Pandas", "CSV-Encoding"),
        debug_turns=1,
    )
    assert distiller.distill(candidate) is None
    candidate = replace(candidate, debug_turns=2)
    capsule = distiller.distill(candidate)
    assert capsule is not None
    assert capsule.source_domain_tags == ("python", "pandas", "csv-encoding")
    serialized = KnowledgeCapsuleSpec.model_validate_json(capsule.model_dump_json())
    assert serialized.capsule_id == capsule.capsule_id


def test_scope_firewall_allows_crew_peer_and_blocks_restricted_crew() -> None:
    tenant_id, workspace_id = uuid4(), uuid4()
    capsule = _capsule(tenant_id, workspace_id)
    policy = LearningPolicy("data_coder", "data_analyst", PropagationScope.CREW_LOCAL)
    firewall = ScopeFirewall()
    data_target = AgentLearningContext(
        "data_analyst", ("python", "pandas"), "Parse and validate a CSV dataset.",
        tenant_id, workspace_id,
    )
    allowed = firewall.authorize(capsule, data_target, policy, same_crew=True)
    assert allowed.allowed
    assert allowed.capsule is not None

    restricted_target = AgentLearningContext(
        "finance_legal_reviewer", ("finance", "legal"), "Review confidential investment terms.",
        tenant_id, workspace_id,
    )
    blocked = firewall.authorize(
        capsule,
        restricted_target,
        LearningPolicy("data_coder", "finance_legal_reviewer", PropagationScope.CREW_LOCAL),
        same_crew=False,
    )
    assert not blocked.allowed
    assert "crew" in blocked.reason


def test_firewall_redacts_credentials_names_and_contact_values() -> None:
    tenant_id, workspace_id = uuid4(), uuid4()
    capsule = KnowledgeCapsuleSpec(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        capsule_id=uuid4(),
        source_agent_id="a",
        source_role="Analyst",
        trigger_preconditions="When handling customer export.",
        distilled_heuristic="Use nx-sk-0123456789ABCDEF for Alice Example at alice@example.com",
        propagation_scope=PropagationScope.WORKSPACE_VERIFIED,
    )
    cleaned = sanitize_capsule(capsule, ("Alice Example",))
    assert "nx-sk-" not in cleaned.distilled_heuristic
    assert "alice@example.com" not in cleaned.distilled_heuristic
    assert "Alice Example" not in cleaned.distilled_heuristic
    assert "[REDACTED]" in cleaned.distilled_heuristic


def test_negative_transfer_score_trips_pair_circuit_breaker_threshold() -> None:
    capsule_id = uuid4()
    baseline = tuple(TransferObservation(True, 0, False, 100, 200) for _ in range(5))
    treatment = tuple(TransferObservation(False, 4, True, 200, 600) for _ in range(5))
    result = score_transfer_pair(
        capsule_id,
        "data_analyst",
        baseline,
        treatment,
        DetectorConfig(threshold=0.15, minimum_applications=5),
    )
    assert result.impact.score < -0.99
    assert result.negative_transfer
    assert result.quarantined
    assert result.sample_count == 5


def test_workflow_learning_edge_serialization_and_validation() -> None:
    tenant_id, workspace_id = uuid4(), uuid4()
    workflow = WorkflowSpec(
        id=uuid4(), tenant_id=tenant_id, workspace_id=workspace_id, name="Data workflow", version=1,
        nodes=(
            StartNodeSpec(id="start"),
            CrewNodeSpec(
                id="data", kind="crew", label="Data crew",
                agents=(AgentSpec(id="data_coder", role="Coder", goal="Parse CSV", model="local/model"),
                        AgentSpec(id="data_analyst", role="Analyst", goal="Review CSV", model="local/model")),
                tasks=(
                    TaskSpec(id="task1", agent_id="data_coder", description="Parse CSV", expected_output="Rows", output_schema="NexusTextResult"),
                    TaskSpec(id="task2", agent_id="data_analyst", description="Review CSV", expected_output="Review", output_schema="NexusTextResult"),
                ),
            ),
        ),
        edges=(WorkflowEdgeSpec(source="start", target="data"),),
        learning_edges=(LearningEdgeSpec(source_agent_id="data_coder", target_agent_id="data_analyst"),),
    )
    restored = WorkflowSpec.model_validate_json(workflow.model_dump_json())
    assert restored.learning_edges[0].source_agent_id == "data_coder"


def test_learning_transfer_api_routes_are_registered_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/learning-transfer/capsules" in paths
    assert "/api/v1/learning-transfer/policies" in paths
    assert {"get", "post"}.issubset(paths["/api/v1/learning-transfer/telemetry"])
