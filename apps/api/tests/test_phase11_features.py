from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from consensus.engine import ConsensusEngine
from flows.state import WorkflowState
from learning_transfer.self_healing import SelfHealingOptimizer
from nexus_core_schema.models import ConsensusConfigSpec
from nexus_model_gateway.auto_distill import DistillationScore, GoldenTrace, GoldenTraceCollector
from time_travel.replay import fork_state, rewind_state


def test_self_healing_produces_diff_and_quarantined_capsule() -> None:
    result = SelfHealingOptimizer().analyze(
        "The report has 3 rows", "The report has 4 rows", "Count every non-empty record before summarizing.",
        target_field="task_description", agent_id="csv_analyst",
    )
    assert "original_output" in result.output_diff
    assert "task_description" in result.proposal.unified_diff
    assert "Count every non-empty record" in result.proposal.after
    assert result.proposal.knowledge_capsule is not None
    assert result.proposal.knowledge_capsule["propagation_scope"] == "WORKSPACE_QUARANTINE"


def test_replay_and_fork_keep_scope_and_completed_prefix() -> None:
    tenant_id, workspace_id, workflow_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    state = WorkflowState(
        id=run_id, run_id=run_id, workflow_id=workflow_id, tenant_id=tenant_id,
        workspace_id=workspace_id, input_data={"x": 1}, node_outputs={"first": {"ok": True}},
        completed_nodes=["start", "first"], status="completed",
    )
    replay = rewind_state(state, mutated_state={"input_data": {"x": 2}}, node_overrides={"prompt": "Recheck input"})
    assert replay.state.run_id != run_id
    assert replay.state.completed_nodes == ["start", "first"]
    assert replay.state.tenant_id == tenant_id and replay.state.workspace_id == workspace_id
    a, b = fork_state(state, {"model": "openai/a"}, {"model": "openai/b"})
    assert a.run_id != b.run_id
    assert a.state.completed_nodes == b.state.completed_nodes
    try:
        rewind_state(state, mutated_state={"tenant_id": str(uuid4())})
    except ValueError:
        pass
    else:
        raise AssertionError("Replay must not allow tenant scope mutation")


def test_golden_trace_threshold_scoring_and_shadow_few_shot() -> None:
    collector = GoldenTraceCollector(minimum_traces=2)
    for index in range(2):
        trace = GoldenTrace("agent", "csv-summary-v1", {"row": index}, {"count": index}, "openai/gpt-4o", 0.01)
        assert collector.record(trace, pydantic_valid=True, human_approved=True, retries=0) is (index == 1)
    score = collector.score("agent", "csv-summary-v1", "openai/gpt-4o-mini",
                            schema_validity_rate=1.0, semantic_similarity=0.97,
                            frontier_latency_ms=1000, candidate_latency_ms=500,
                            frontier_cost_usd=0.01, candidate_cost_usd=0.004)
    assert score.eligible and score.latency_speedup == 2

    async def evaluator(model: str, traces: Sequence[GoldenTrace], examples: Sequence[dict[str, Any]]) -> DistillationScore:
        assert len(traces) == 2 and len(examples) == 2
        return score

    evaluated = asyncio.run(collector.evaluate("agent", "csv-summary-v1", ["openai/gpt-4o-mini"], evaluator))
    assert evaluated == (score,)


def test_consensus_arbitrates_and_flags_low_agreement() -> None:
    async def execute(model: str) -> str:
        return "answer A" if model == "model-a" else "answer B"

    async def critique(left: object, right: object) -> str:
        return "Different totals; verify source rows."

    async def arbitrate(drafts: object, critiques: object) -> tuple[str, float]:
        return "Count verified source rows and report uncertainty.", 0.62

    result = asyncio.run(ConsensusEngine(execute, critique, arbitrate).run(["model-a", "model-b"], 0.85))
    assert result.approval_required
    assert len(result.drafts) == 2 and "Different totals" in result.dissent_report
    assert ConsensusConfigSpec(enabled=True, models=("a", "b"), arbiter_model="judge").min_agreement_threshold == 0.85


def test_phase11_api_routes_and_tenant_scoped_tables_are_registered() -> None:
    from app.main import create_app
    from app.models import Base, DistillationRecommendation, GoldenTraceRecord, PromptPatchProposal

    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    assert "/api/v1/self-healing/proposals" in paths
    assert "/api/v1/runs/{run_id}/checkpoints/{checkpoint_id}/rewind" in paths
    assert "/api/v1/runs/{run_id}/checkpoints/{checkpoint_id}/fork" in paths
    assert "/api/v1/runs/compare" in paths
    for model in (PromptPatchProposal, GoldenTraceRecord, DistillationRecommendation):
        assert {"tenant_id", "workspace_id"} <= set(model.__table__.columns.keys())
        assert model.__tablename__ in Base.metadata.tables
