"""Rolling baseline/treatment comparison and per-target circuit breaker."""

from __future__ import annotations

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
