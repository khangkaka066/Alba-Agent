"""Product fitness of a team generation, aggregation across runs and the automatic rollback rule."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nexus_core_schema.models import AutoGenSandboxNodeSpec, CrewNodeSpec, RouterNodeSpec, WorkflowSpec

W_COMPLETENESS = 0.45
W_QUALITY = 0.35
W_EFFICIENCY = 0.20
ROLLBACK_MARGIN = 0.05
RECOVERED_CREDIT = 0.75
MIN_RUNS_FOR_DECISION = 1
APPROVAL_SCORES = {"allowed_once": 1.0, "always_allowed": 1.0, "denied": 0.0}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class RunMetrics:
    completeness: float
    qa_score: float
    human_rating: float | None
    cost_usd: float
    latency_seconds: float
    completed: bool


@dataclass(frozen=True)
class GenerationStats:
    runs: int
    artifact_completeness: float
    quality: float
    human_rating: float | None
    cost_usd: float
    latency_seconds: float


@dataclass(frozen=True)
class RollbackDecision:
    rollback: bool
    child_fitness: float
    parent_fitness: float
    reason: str


def extract_run_metrics(
    spec: WorkflowSpec,
    status: str,
    node_outputs: Mapping[str, Any],
    completed_nodes: Sequence[str],
    approval_statuses: Sequence[str] = (),
    cost_usd: float = 0.0,
    latency_seconds: float = 0.0,
) -> RunMetrics:
    """Measure one run: how much of the declared product exists, how good it was judged, and what it cost."""
    declared: list[tuple[str, str]] = []
    for node in spec.nodes:
        if isinstance(node, (CrewNodeSpec, AutoGenSandboxNodeSpec)):
            declared += [(node.id, path) for path in node.declared_artifact_paths()]
    completed = status == "completed"
    if declared:
        credit = 0.0
        for node_id, path in declared:
            contract = node_outputs.get(node_id, {}).get("artifact_contract") if isinstance(node_outputs.get(node_id), Mapping) else None
            if not isinstance(contract, Mapping):
                continue
            if path in contract.get("verified", ()):
                credit += 1.0
            elif path in contract.get("recovered", ()):
                credit += RECOVERED_CREDIT
        completeness = credit / len(declared)
    else:
        completeness = (1.0 if completed else len(set(completed_nodes)) / max(1, len(spec.nodes)))

    signals: list[float] = []
    for node in spec.nodes:
        if isinstance(node, RouterNodeSpec) and node.artifact_gate:
            verdict = node_outputs.get(node.gate_key())
            loops = node_outputs.get(f"{node.id}__loops", 0)
            if isinstance(verdict, Mapping):
                base = 1.0 if verdict.get("gate_passed") else 0.0
                signals.append(clamp(base - 0.25 * float(loops if isinstance(loops, (int, float)) else 0)))
    confidences = [
        float(value) for output in node_outputs.values() if isinstance(output, Mapping)
        for key in ("evaluation_confidence", "confidence", "consensus_confidence")
        if isinstance(value := output.get(key), (int, float)) and 0 <= float(value) <= 1
    ]
    if confidences:
        signals.append(sum(confidences) / len(confidences))
    qa = sum(signals) / len(signals) if signals else (1.0 if completed else 0.0)
    scores = [APPROVAL_SCORES[item] for item in approval_statuses if item in APPROVAL_SCORES]
    human = sum(scores) / len(scores) if scores else None
    return RunMetrics(clamp(completeness), clamp(qa), human, max(0.0, cost_usd), max(0.0, latency_seconds), completed)


def aggregate(runs: Sequence[RunMetrics]) -> GenerationStats | None:
    if not runs:
        return None
    ratings = [run.human_rating for run in runs if run.human_rating is not None]
    return GenerationStats(
        runs=len(runs),
        artifact_completeness=sum(run.completeness for run in runs) / len(runs),
        quality=sum(run.qa_score for run in runs) / len(runs),
        human_rating=sum(ratings) / len(ratings) if ratings else None,
        cost_usd=sum(run.cost_usd for run in runs) / len(runs),
        latency_seconds=sum(run.latency_seconds for run in runs) / len(runs),
    )


def quality_score(stats: GenerationStats) -> float:
    """QAAndHumanQualityScore: the QA verdict, averaged with reviewer approval when a human reviewed the run."""
    return clamp(stats.quality if stats.human_rating is None else (stats.quality + stats.human_rating) / 2)


def efficiency(stats: GenerationStats, reference: GenerationStats | None) -> float:
    """CostAndLatencyEfficiency relative to the lineage's first generation (which scores 1.0 by definition)."""
    if reference is None:
        return 1.0

    def ratio(observed: float, baseline: float) -> float:
        if observed <= 0 or baseline <= 0:
            return 1.0
        return clamp(baseline / observed)

    return clamp(0.5 * ratio(stats.cost_usd, reference.cost_usd) + 0.5 * ratio(stats.latency_seconds, reference.latency_seconds))


def product_fitness(stats: GenerationStats, reference: GenerationStats | None = None) -> float:
    """Fitness(V_k) = 0.45 * ArtifactCompleteness + 0.35 * QAAndHumanQualityScore + 0.20 * CostAndLatencyEfficiency."""
    return clamp(
        W_COMPLETENESS * stats.artifact_completeness + W_QUALITY * quality_score(stats) + W_EFFICIENCY * efficiency(stats, reference),
    )


class FitnessTracker:
    """Decides whether an evolved generation must be rolled back to its parent."""

    def __init__(self, margin: float = ROLLBACK_MARGIN, min_runs: int = MIN_RUNS_FOR_DECISION) -> None:
        self._margin = margin
        self._min_runs = min_runs

    def evaluate(self, child: GenerationStats | None, parent: GenerationStats | None, reference: GenerationStats | None) -> RollbackDecision:
        if child is None or parent is None:
            return RollbackDecision(False, 0.0, 0.0, "Not enough observations on both generations to compare.")
        child_fitness, parent_fitness = product_fitness(child, reference), product_fitness(parent, reference)
        if child.runs < self._min_runs or parent.runs < self._min_runs:
            return RollbackDecision(False, child_fitness, parent_fitness, "Waiting for more runs before judging this generation.")
        if child_fitness < parent_fitness - self._margin:
            return RollbackDecision(
                True, child_fitness, parent_fitness,
                f"Fitness {child_fitness:.3f} fell more than {self._margin:.2f} below the parent's {parent_fitness:.3f}.",
            )
        return RollbackDecision(False, child_fitness, parent_fitness, f"Fitness {child_fitness:.3f} holds against the parent's {parent_fitness:.3f}.")
