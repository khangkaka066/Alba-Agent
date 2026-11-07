"""Golden trace collection and deterministic shadow evaluation scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Sequence


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


# ---------------------------------------------------------------------------------------------------------------------------------
# Breadth-depth allocation and compute accounting (arXiv:2608.05643, Sec. 3.5, Table 3, Appendix A.7).
#
# What the paper gives us: generation compute C_gen = sum over calls of 2 P_gen (T_in + T_out) FLOPs, and the compute-normalized gain
# eta = 10^3 (a_refined - a_base) / (C_refined - C_base) in accuracy points per 10^3 TFLOPs (Eq. 10). Its Table 3 shows accuracy is
# NOT monotonic in the breadth N or the depth D, and it recommends moderate settings (N = 8, D = 4 was stable); it also finds the
# gain per unit of compute largest for the SMALLEST models (A.8). The tier table below is our heuristic built on that, not a result
# of the paper, and is only ever a SUGGESTION: whether refinement runs at all is a separate, opt-in decision.
# ---------------------------------------------------------------------------------------------------------------------------------

ModelTier = Literal["tiny", "small", "mid", "frontier"]

# Whole words of the model name, not substrings: "gemini" contains "mini" but is not a mini model.
_SMALL_WORDS = frozenset({"nano", "mini", "flash", "haiku", "lite", "small"})
_FRONTIER_WORDS = frozenset({"opus", "sonnet", "fable", "pro", "o3", "o4"})
_FRONTIER_PREFIXES = ("gpt-5", "gpt-6")
_WORDS = re.compile(r"[a-z0-9.]+")
_MIXTURE = re.compile(r"(\d+)x(\d+(?:\.\d+)?)b(?![a-z])")
_SIZE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)b(?![a-z])")


def estimated_parameters_b(model: str) -> float | None:
    """Billions of parameters read from the model name ("qwen2.5:1.5b", "llama3.1-8b", "mixtral-8x7b"); None when it has none."""
    name = model.lower().rsplit("/", 1)[-1]
    mixture = _MIXTURE.search(name)
    if mixture:
        return int(mixture.group(1)) * float(mixture.group(2))
    size = _SIZE.search(name)
    return float(size.group(1)) if size else None


def classify_model_tier(model: str, parameters_b: float | None = None) -> ModelTier:
    """tiny (<= 3B), small (<= 10B, or a mini / nano / flash / haiku name), mid (<= 80B or unknown), frontier (larger or a flagship)."""
    size = parameters_b if parameters_b is not None else estimated_parameters_b(model)
    if size is not None:
        return "tiny" if size <= 3 else "small" if size <= 10 else "mid" if size <= 80 else "frontier"
    name = model.lower().rsplit("/", 1)[-1]
    words = set(_WORDS.findall(name))
    if words & _SMALL_WORDS:
        return "small"
    if words & _FRONTIER_WORDS or name.startswith(_FRONTIER_PREFIXES):
        return "frontier"
    return "mid"


@dataclass(frozen=True)
class BreadthDepth:
    breadth: int
    depth: int

    def __post_init__(self) -> None:
        if self.breadth < 1 or self.depth < 1:
            raise ValueError("breadth and depth must be at least 1")

    @property
    def planned_calls(self) -> int:
        """N initial rollouts plus generate, critique and correct for each of the N rollouts at each of the D depths."""
        return self.breadth + 3 * self.breadth * self.depth


def allocate_breadth_depth(tier: ModelTier, *, hard_task: bool = False) -> BreadthDepth:
    """A suggested (N, D): deeper for smaller models, lean for flagships on plain tasks. Never a reason to run refinement by itself."""
    if tier == "tiny":
        return BreadthDepth(8, 4)
    if tier == "small":
        return BreadthDepth(8, 4) if hard_task else BreadthDepth(5, 3)
    if tier == "mid":
        return BreadthDepth(3, 2)
    return BreadthDepth(3, 2) if hard_task else BreadthDepth(1, 1)


def fit_to_call_budget(plan: BreadthDepth, max_calls: int | None) -> BreadthDepth:
    """The largest plan within `max_calls` model calls: the depth is trimmed first, then the breadth. Raises when even (1, 1) is too big."""
    if max_calls is None or plan.planned_calls <= max_calls:
        return plan
    breadth, depth = plan.breadth, plan.depth
    while BreadthDepth(breadth, depth).planned_calls > max_calls:
        if depth > 1:
            depth -= 1
        elif breadth > 1:
            breadth -= 1
        else:
            raise ValueError(f"{max_calls} model calls cannot pay for even one rollout and one refinement step ({BreadthDepth(1, 1).planned_calls})")
    return BreadthDepth(breadth, depth)


def generation_flops(parameters_b: float, tokens_in: int, tokens_out: int) -> float:
    """2 P (T_in + T_out) floating-point operations for one autoregressive call of a model with P = parameters_b billion parameters."""
    if parameters_b <= 0 or tokens_in < 0 or tokens_out < 0:
        raise ValueError("parameters_b must be positive and token counts non-negative")
    return 2.0 * parameters_b * 1e9 * (tokens_in + tokens_out)


@dataclass(frozen=True)
class CallRecord:
    model: str
    role: str
    tokens_in: int
    tokens_out: int
    usd: float = 0.0
    parameters_b: float | None = None


@dataclass
class ComputeLedger:
    """What a run's model calls cost, in tokens, dollars and (when the parameter count is known) TFLOPs."""

    calls: list[CallRecord] = field(default_factory=list)

    def record(self, model: str, role: str, tokens_in: int, tokens_out: int, *, usd: float = 0.0, parameters_b: float | None = None) -> None:
        if tokens_in < 0 or tokens_out < 0 or usd < 0:
            raise ValueError("tokens and cost cannot be negative")
        known = parameters_b if parameters_b is not None else estimated_parameters_b(model)
        self.calls.append(CallRecord(model, role, tokens_in, tokens_out, usd, known))

    @property
    def tokens(self) -> int:
        return sum(call.tokens_in + call.tokens_out for call in self.calls)

    @property
    def usd(self) -> float:
        return sum(call.usd for call in self.calls)

    @property
    def tflops(self) -> float | None:
        """Total TFLOPs, or None when any call is to a model whose size is not known (hosted models do not publish it)."""
        if not self.calls or any(call.parameters_b is None for call in self.calls):
            return None
        return sum(generation_flops(call.parameters_b, call.tokens_in, call.tokens_out) for call in self.calls if call.parameters_b is not None) / 1e12


def compute_normalized_gain(accuracy_refined: float, accuracy_base: float, compute_refined: float, compute_base: float, *, scale: float = 1e3) -> float | None:
    """eta = scale * (a_refined - a_base) / (C_refined - C_base), Eq. (10). Accuracy is in points (0-100); None when no extra compute was spent."""
    extra = compute_refined - compute_base
    if extra <= 0:
        return None
    return scale * (accuracy_refined - accuracy_base) / extra


@dataclass(frozen=True)
class GainReport:
    eta: float | None
    unit: Literal["tflops", "usd", "tokens"]
    delta_accuracy: float
    delta_compute: float


def gain_report(refined: ComputeLedger, base: ComputeLedger, accuracy_refined: float, accuracy_base: float) -> GainReport:
    """eta on the best unit both ledgers can state: TFLOPs (the paper's), else dollars, else tokens. The unit is part of the answer:
    hosted models do not publish their size, so their eta is per 10^3 dollars or tokens and cannot be compared with the paper's."""
    if refined.tflops is not None and base.tflops is not None:
        unit: Literal["tflops", "usd", "tokens"] = "tflops"
        c_refined, c_base = refined.tflops, base.tflops
    elif refined.usd > 0 and base.usd > 0:
        unit, c_refined, c_base = "usd", refined.usd, base.usd
    else:
        unit, c_refined, c_base = "tokens", float(refined.tokens), float(base.tokens)
    return GainReport(compute_normalized_gain(accuracy_refined, accuracy_base, c_refined, c_base), unit, accuracy_refined - accuracy_base, c_refined - c_base)
