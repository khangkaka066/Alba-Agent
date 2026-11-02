"""Golden trace collection and deterministic shadow evaluation scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Sequence


@dataclass(frozen=True)
class GoldenTrace:
    agent_id: str
    task_signature: str
    input_payload: dict[str, Any]
    verified_output: Any
    model_used: str
    cost_usd: float


@dataclass(frozen=True)
class DistillationScore:
    model: str
    schema_validity_rate: float
    semantic_similarity: float
    latency_speedup: float
    cost_reduction: float

    @property
    def eligible(self) -> bool:
        return self.schema_validity_rate >= 0.95 and self.semantic_similarity >= 0.95 and self.cost_reduction >= 0.40


class GoldenTraceCollector:
    def __init__(self, minimum_traces: int = 20) -> None:
        if minimum_traces < 1:
            raise ValueError("minimum_traces must be positive")
        self.minimum_traces = minimum_traces
        self._traces: dict[tuple[str, str], list[GoldenTrace]] = {}
        self._recommendations: dict[tuple[str, str], DistillationScore] = {}

    def record(self, trace: GoldenTrace, *, pydantic_valid: bool, human_approved: bool, retries: int) -> bool:
        if not pydantic_valid or not human_approved or retries != 0:
            return False
        self._traces.setdefault((trace.agent_id, trace.task_signature), []).append(trace)
        return len(self._traces[(trace.agent_id, trace.task_signature)]) >= self.minimum_traces

    def traces(self, agent_id: str, task_signature: str) -> tuple[GoldenTrace, ...]:
        return tuple(self._traces.get((agent_id, task_signature), ()))

    @staticmethod
    def few_shot_examples(traces: Sequence[GoldenTrace], limit: int = 3) -> tuple[dict[str, Any], ...]:
        return tuple({"input": t.input_payload, "output": t.verified_output} for t in traces[-limit:])

    def score(self, agent_id: str, task_signature: str, model: str, *, schema_validity_rate: float,
              semantic_similarity: float, frontier_latency_ms: float, candidate_latency_ms: float,
              frontier_cost_usd: float, candidate_cost_usd: float) -> DistillationScore:
        values = (schema_validity_rate, semantic_similarity)
        if any(not 0 <= value <= 1 for value in values) or min(frontier_latency_ms, candidate_latency_ms, frontier_cost_usd) < 0:
            raise ValueError("Invalid shadow evaluation metrics")
        cost_reduction = 0.0 if frontier_cost_usd == 0 else 1 - candidate_cost_usd / frontier_cost_usd
        speedup = 0.0 if candidate_latency_ms <= 0 else frontier_latency_ms / candidate_latency_ms
        result = DistillationScore(model, schema_validity_rate, semantic_similarity, speedup, cost_reduction)
        if result.eligible:
            self._recommendations[(agent_id, task_signature)] = result
        return result

    async def evaluate(self, agent_id: str, task_signature: str, candidates: Sequence[str],
                       evaluator: Callable[[str, Sequence[GoldenTrace], Sequence[dict[str, Any]]], Awaitable[DistillationScore]]) -> tuple[DistillationScore, ...]:
        traces = self.traces(agent_id, task_signature)
        if len(traces) < self.minimum_traces:
            return ()
        examples = self.few_shot_examples(traces)
        return tuple(await __import__("asyncio").gather(*(evaluator(model, traces, examples) for model in candidates)))

    def recommendations(self) -> tuple[tuple[str, str, DistillationScore], ...]:
        return tuple((agent, signature, score) for (agent, signature), score in self._recommendations.items())
