"""Rolling baseline/treatment comparison and per-target circuit breaker."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Callable, Literal
from uuid import UUID


@dataclass(frozen=True)
class TransferObservation:
    success: bool
    retry_and_error_turns: int
    human_approval_rejected: bool
    token_count: int
    latency_ms: int = 0


@dataclass(frozen=True)
class TransferImpactScore:
    score: float
    success_delta: float
    retry_delta: float
    rejection_delta: float
    token_overhead_delta: float
    latency_delta: float


@dataclass(frozen=True)
class DetectorConfig:
    threshold: float = 0.15
    minimum_applications: int = 5
    success_weight: float = 0.45
    retry_weight: float = 0.25
    rejection_weight: float = 0.2
    token_weight: float = 0.1

    def __post_init__(self) -> None:
        if not 0 < self.threshold <= 1 or self.minimum_applications < 1:
            raise ValueError("Invalid negative-transfer detector threshold")
        if min(self.success_weight, self.retry_weight, self.rejection_weight, self.token_weight) < 0:
            raise ValueError("Transfer weights cannot be negative")
        if abs(self.success_weight + self.retry_weight + self.rejection_weight + self.token_weight - 1) > 1e-8:
            raise ValueError("Transfer weights must sum to one")


@dataclass(frozen=True)
class TransferPairDecision:
    capsule_id: UUID
    target_agent_id: str
    sample_count: int
    impact: TransferImpactScore
    negative_transfer: bool
    quarantined: bool


TransferOutcome = Literal["positive", "neutral", "negative", "insufficient_data"]


def _mean(observations: tuple[TransferObservation, ...], fn: Callable[[TransferObservation], float]) -> float:
    return fmean(fn(item) for item in observations)


def score_transfer_pair(
    capsule_id: UUID,
    target_agent_id: str,
    baseline: tuple[TransferObservation, ...],
    treatment: tuple[TransferObservation, ...],
    config: DetectorConfig = DetectorConfig(),
) -> TransferPairDecision:
    sample_count = len(treatment)
    if not baseline or not treatment:
        empty_impact = TransferImpactScore(0, 0, 0, 0, 0, 0)
        return TransferPairDecision(capsule_id, target_agent_id, sample_count, empty_impact, False, False)
    success_delta = _mean(treatment, lambda item: float(item.success)) - _mean(baseline, lambda item: float(item.success))
    retry_delta = _mean(treatment, lambda item: float(item.retry_and_error_turns)) - _mean(baseline, lambda item: float(item.retry_and_error_turns))
    rejection_delta = _mean(treatment, lambda item: float(item.human_approval_rejected)) - _mean(baseline, lambda item: float(item.human_approval_rejected))
    baseline_tokens = _mean(baseline, lambda item: float(item.token_count))
    token_delta = (_mean(treatment, lambda item: float(item.token_count)) - baseline_tokens) / max(1.0, baseline_tokens)
    baseline_latency = _mean(baseline, lambda item: float(item.latency_ms))
    latency_delta = (_mean(treatment, lambda item: float(item.latency_ms)) - baseline_latency) / max(1.0, baseline_latency)
    # Bounded contributions keep incomparable retry/token scales from dominating.
    retry_penalty = max(-1.0, min(1.0, retry_delta / max(1.0, _mean(baseline, lambda item: float(item.retry_and_error_turns)) + 1)))
    efficiency_penalty = max(-1.0, min(1.0, (token_delta + latency_delta) / 2))
    impact_score = max(-1.0, min(1.0, config.success_weight * success_delta - config.retry_weight * retry_penalty - config.rejection_weight * rejection_delta - config.token_weight * efficiency_penalty))
    impact = TransferImpactScore(impact_score, success_delta, retry_delta, rejection_delta, token_delta, latency_delta)
    negative = sample_count >= config.minimum_applications and impact_score < -config.threshold
    return TransferPairDecision(capsule_id, target_agent_id, sample_count, impact, negative, negative)


# ---------------------------------------------------------------------------------------------------------------------------------
# Recovery / regression dynamics (arXiv:2608.05643, Appendix A.2 and A.3, Eq. 6-9).
#
# Two different families of rates, which the paper keeps apart and so do we:
#   * question level, Eq. (6)-(7): rho_rec(d) and rho_reg(d), the share of questions whose FINAL (plurality-vote) answer flipped from
#     wrong to correct / from correct to wrong between depth d-1 and d. They explain the accuracy change: dA(d) = rho_rec - rho_reg.
#   * trace level, Eq. (8)-(9): mu_{W->C}(d) and mu_{C->W}(d), the share of single (question, rollout) traces that flipped, and the
#     net correction benefit B(d) = mu_{W->C} - mu_{C->W}.
# The paper warns that a negative trace-level B(d) "does not necessarily imply lower final accuracy": plurality voting suppresses
# isolated harmful flips. A rule "B < 0, so quarantine" would therefore flag steps that help overall. `assess_flips` asks for enough
# data, an exact sign test, and (when given) the final-outcome rates, and only RECOMMENDS: a person decides.
# Whether a trace is "correct" needs an oracle (the paper has gold answers; here a verified result or an approval).
# ---------------------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TraceTransition:
    """The same trace judged right before and right after a step (a critique, a skill, a capsule) was applied to it."""

    trace_id: str
    before_correct: bool
    after_correct: bool
    depth: int = 1


@dataclass(frozen=True)
class FlipRates:
    pairs: int
    wrong_to_correct: int
    correct_to_wrong: int
    mu_wrong_to_correct: float
    mu_correct_to_wrong: float
    net_benefit: float


def flip_rates(transitions: Sequence[TraceTransition], depth: int | None = None) -> FlipRates:
    """mu_{W->C}(d), mu_{C->W}(d) and B(d) over all pairs at depth `depth` (all depths together when None). Eq. (8)-(9)."""
    chosen = [item for item in transitions if depth is None or item.depth == depth]
    total = len(chosen)
    recovered = sum(1 for item in chosen if not item.before_correct and item.after_correct)
    regressed = sum(1 for item in chosen if item.before_correct and not item.after_correct)
    if total == 0:
        return FlipRates(0, 0, 0, 0.0, 0.0, 0.0)
    return FlipRates(total, recovered, regressed, recovered / total, regressed / total, (recovered - regressed) / total)


@dataclass(frozen=True)
class DepthRates:
    """Question-level figures at depth d: accuracy A(d), improvement dA(d), rho_rec(d) and rho_reg(d)."""

    depth: int
    questions: int
    accuracy: float
    delta_accuracy: float
    recovery: float
    regression: float


def question_level_rates(correctness: Sequence[Sequence[bool]]) -> list[DepthRates]:
    """Eq. (6)-(7) from one row per question: [delta(0), delta(1), ..., delta(D)], delta(d) = is the depth-d plurality answer correct.

    delta(0) is the answer before any refinement. Returns one entry per depth d = 1..D. By construction dA(d) = rho_rec - rho_reg.
    """
    if not correctness:
        return []
    width = len(correctness[0])
    if width < 2 or any(len(row) != width for row in correctness):
        raise ValueError("Every question needs the same number of depths, at least delta(0) and delta(1)")
    questions = len(correctness)
    rates: list[DepthRates] = []
    for d in range(1, width):
        accuracy = sum(row[d] for row in correctness) / questions
        previous = sum(row[d - 1] for row in correctness) / questions
        recovery = sum(1 for row in correctness if not row[d - 1] and row[d]) / questions
        regression = sum(1 for row in correctness if row[d - 1] and not row[d]) / questions
        rates.append(DepthRates(d, questions, accuracy, accuracy - previous, recovery, regression))
    return rates


@dataclass(frozen=True)
class FlipAssessmentConfig:
    minimum_pairs: int = 30
    minimum_discordant: int = 8
    alpha: float = 0.05

    def __post_init__(self) -> None:
        if self.minimum_pairs < 1 or self.minimum_discordant < 1 or not 0 < self.alpha < 1:
            raise ValueError("Invalid flip assessment settings")


@dataclass(frozen=True)
class FlipAssessment:
    rates: FlipRates
    p_harm: float | None
    p_benefit: float | None
    verdict: TransferOutcome
    recommend_quarantine: bool
    requires_human_approval: bool
    reason: str


def _upper_tail(successes: int, trials: int) -> float:
    """P(X >= successes) for X ~ Binomial(trials, 1/2): the exact one-sided sign test."""
    if trials == 0:
        return 1.0
    return sum(math.comb(trials, k) for k in range(successes, trials + 1)) / (1 << trials)


def assess_flips(
    transitions: Sequence[TraceTransition],
    config: FlipAssessmentConfig = FlipAssessmentConfig(),
    final_outcomes: Sequence[TraceTransition] | None = None,
) -> FlipAssessment:
    """Is applying this step / skill / capsule harming traces? Needs a pair per trace; returns a recommendation, never an action.

    Negative: enough pairs, enough flips either way, B < 0 and C->W exceeds W->C by an exact one-sided sign test at `alpha`. With
    `final_outcomes` (the same step judged on the FINAL answers) a trace-level harm that the final answers do not show is NOT
    flagged, because the paper (A.3) says plurality voting absorbs such flips.
    """
    rates = flip_rates(transitions)
    discordant = rates.wrong_to_correct + rates.correct_to_wrong
    if rates.pairs < config.minimum_pairs or discordant < config.minimum_discordant:
        return FlipAssessment(rates, None, None, "insufficient_data", False, True,
                              f"{rates.pairs} pairs and {discordant} flips; at least {config.minimum_pairs} and {config.minimum_discordant} are needed")
    p_harm = _upper_tail(rates.correct_to_wrong, discordant)
    p_benefit = _upper_tail(rates.wrong_to_correct, discordant)
    if rates.net_benefit < 0 and p_harm <= config.alpha:
        if final_outcomes is not None:
            final = flip_rates(final_outcomes)
            if final.pairs and final.net_benefit >= 0:
                return FlipAssessment(rates, p_harm, p_benefit, "neutral", False, True,
                                      f"traces regress (B={rates.net_benefit:.3f}) but the final answers do not (B={final.net_benefit:.3f}); "
                                      "majority voting absorbs it")
        return FlipAssessment(rates, p_harm, p_benefit, "negative", True, True,
                              f"B={rates.net_benefit:.3f}: {rates.correct_to_wrong} correct->wrong against {rates.wrong_to_correct} wrong->correct, p={p_harm:.4f}")
    if rates.net_benefit > 0 and p_benefit <= config.alpha:
        return FlipAssessment(rates, p_harm, p_benefit, "positive", False, True,
                              f"B={rates.net_benefit:.3f}: {rates.wrong_to_correct} wrong->correct against {rates.correct_to_wrong} correct->wrong, p={p_benefit:.4f}")
    return FlipAssessment(rates, p_harm, p_benefit, "neutral", False, True, f"B={rates.net_benefit:.3f} is not distinguishable from zero")


def flag_for_review(decision: TransferPairDecision, assessment: FlipAssessment) -> bool:
    """A capsule goes to a person when EITHER signal says negative: the impact score of `score_transfer_pair` or the flip test."""
    return decision.negative_transfer or assessment.recommend_quarantine
