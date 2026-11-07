"""Breadth-depth allocation by model tier, compute accounting and the compute-normalized gain (arXiv:2608.05643, Sec. 3.5, A.7)."""

from __future__ import annotations

import pytest

from nexus_model_gateway.auto_distill import (
    BreadthDepth,
    ComputeLedger,
    ModelTier,
    allocate_breadth_depth,
    classify_model_tier,
    compute_normalized_gain,
    estimated_parameters_b,
    fit_to_call_budget,
    gain_report,
    generation_flops,
)


@pytest.mark.parametrize(("model", "size"), [
    ("qwen2.5:1.5b", 1.5), ("llama3.1-8b", 8.0), ("ollama/gemma2:9b-instruct", 9.0), ("mixtral-8x7b", 56.0), ("phi3:3.8b", 3.8),
    ("meta/llama-3.1-70b-instruct", 70.0), ("gpt-4.1-mini", None), ("claude-3-5-haiku-20241022", None), ("gpt-6-luna", None),
])
def test_parameter_count_is_read_from_the_model_name(model: str, size: float | None) -> None:
    assert estimated_parameters_b(model) == size


@pytest.mark.parametrize(("model", "tier"), [
    ("qwen2.5:1.5b", "tiny"), ("llama3.1-8b", "small"), ("llama-3.1-70b", "mid"), ("llama-3.1-405b", "frontier"),
    ("openai/gpt-4.1-mini", "small"), ("gpt-4o-mini", "small"), ("claude-3-5-haiku-20241022", "small"), ("gemini-2.5-flash", "small"),
    ("claude-opus-4-5", "frontier"), ("gpt-6-luna", "frontier"), ("gemini-2.5-pro", "frontier"), ("deepseek-chat", "mid"), ("kimi-k3", "mid"),
])
def test_models_are_sorted_into_tiers(model: str, tier: ModelTier) -> None:
    assert classify_model_tier(model) == tier


def test_name_hints_are_whole_words_not_substrings() -> None:
    assert classify_model_tier("gemini-2.5-pro") == "frontier", "'gemini' contains 'mini' but is not a mini model"
    assert classify_model_tier("gemini-2.5-flash-lite") == "small"
    assert classify_model_tier("o3-mini") == "small" and classify_model_tier("o3") == "frontier"
    assert classify_model_tier("promptist-v1") == "mid", "'pro' inside another word is not a hint"


def test_a_known_size_beats_the_name_hints() -> None:
    assert classify_model_tier("some-mini-model", parameters_b=70) == "mid"
    assert classify_model_tier("gpt-6-luna", parameters_b=2) == "tiny"


def test_smaller_models_get_deeper_refinement_and_flagships_stay_lean() -> None:
    assert allocate_breadth_depth("tiny") == BreadthDepth(8, 4)
    assert allocate_breadth_depth("small") == BreadthDepth(5, 3)
    assert allocate_breadth_depth("small", hard_task=True) == BreadthDepth(8, 4)
    assert allocate_breadth_depth("mid") == BreadthDepth(3, 2)
    assert allocate_breadth_depth("frontier") == BreadthDepth(1, 1)
    assert allocate_breadth_depth("frontier", hard_task=True) == BreadthDepth(3, 2)


def test_planned_calls_are_n_plus_three_n_d() -> None:
    assert [BreadthDepth(*pair).planned_calls for pair in ((8, 4), (5, 3), (3, 2), (1, 1))] == [104, 50, 21, 4]


def test_a_plan_is_trimmed_to_a_call_budget_depth_first() -> None:
    assert fit_to_call_budget(BreadthDepth(8, 4), None) == BreadthDepth(8, 4)
    assert fit_to_call_budget(BreadthDepth(8, 4), 104) == BreadthDepth(8, 4)
    assert fit_to_call_budget(BreadthDepth(8, 4), 60) == BreadthDepth(8, 2)
    assert fit_to_call_budget(BreadthDepth(8, 4), 30) == BreadthDepth(7, 1), "depth reaches 1 first, then the breadth shrinks"
    assert fit_to_call_budget(BreadthDepth(8, 4), 4) == BreadthDepth(1, 1)
    with pytest.raises(ValueError):
        fit_to_call_budget(BreadthDepth(8, 4), 3)
    with pytest.raises(ValueError):
        BreadthDepth(0, 1)


def test_generation_flops_follow_two_p_times_tokens() -> None:
    assert generation_flops(1.5, 1000, 500) == pytest.approx(4.5e12), "2 * 1.5e9 * 1500"
    with pytest.raises(ValueError):
        generation_flops(0, 1, 1)


def test_the_ledger_states_tflops_only_when_every_model_size_is_known() -> None:
    local = ComputeLedger()
    local.record("qwen2.5:1.5b", "generate", 1000, 500)
    local.record("qwen2.5:1.5b", "critique", 500, 100, parameters_b=1.5)
    assert local.tflops == pytest.approx(2 * 1.5e9 * 1500 / 1e12 + 2 * 1.5e9 * 600 / 1e12) and local.tokens == 2100
    mixed = ComputeLedger()
    mixed.record("qwen2.5:1.5b", "generate", 10, 10)
    mixed.record("gpt-4o-mini", "generate", 10, 10, usd=0.01)
    assert mixed.tflops is None and mixed.usd == pytest.approx(0.01), "a hosted model's size is unknown, so TFLOPs are not stated"
    assert ComputeLedger().tflops is None
    with pytest.raises(ValueError):
        local.record("m", "generate", -1, 0)


def test_compute_normalized_gain_is_points_per_thousand_units_of_extra_compute() -> None:
    assert compute_normalized_gain(35.0, 25.0, 700.0, 200.0) == pytest.approx(20.0), "1e3 * 10 / 500"
    assert compute_normalized_gain(30.0, 40.0, 700.0, 200.0) == pytest.approx(-20.0), "a loss is a negative gain, not an error"
    assert compute_normalized_gain(30.0, 25.0, 200.0, 200.0) is None and compute_normalized_gain(30.0, 25.0, 100.0, 200.0) is None


def test_the_papers_arithmetic_is_consistent_with_the_formula() -> None:
    """Qwen2.5-1.5B vs Maj@8: 13.21 -> 25.67 points with eta = 17.10 implies about 728.7 extra TFLOPs; the formula inverts cleanly."""
    extra = 1e3 * (25.67 - 13.21) / 17.10
    assert compute_normalized_gain(25.67, 13.21, extra, 0.0) == pytest.approx(17.10)


def test_the_gain_report_names_its_unit() -> None:
    base, refined = ComputeLedger(), ComputeLedger()
    base.record("qwen2.5:1.5b", "generate", 1000, 500)
    refined.record("qwen2.5:1.5b", "generate", 8000, 4000)
    local = gain_report(refined, base, accuracy_refined=40.0, accuracy_base=30.0)
    assert local.unit == "tflops" and local.delta_accuracy == 10.0 and local.eta == pytest.approx(1e3 * 10 / local.delta_compute)

    hosted_base, hosted_refined = ComputeLedger(), ComputeLedger()
    hosted_base.record("gpt-4o-mini", "generate", 1000, 500, usd=0.001)
    hosted_refined.record("gpt-4o-mini", "generate", 9000, 4500, usd=0.011)
    assert gain_report(hosted_refined, hosted_base, 40.0, 30.0).unit == "usd"

    unpriced_base, unpriced_refined = ComputeLedger(), ComputeLedger()
    unpriced_base.record("gpt-4o-mini", "generate", 1000, 500)
    unpriced_refined.record("gpt-4o-mini", "generate", 9000, 4500)
    report = gain_report(unpriced_refined, unpriced_base, 40.0, 30.0)
    assert report.unit == "tokens" and report.delta_compute == 12000.0

    cheaper = gain_report(base, refined, accuracy_refined=40.0, accuracy_base=30.0)
    assert cheaper.eta is None, "no extra compute: the gain per unit of compute is undefined"
