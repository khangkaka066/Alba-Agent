"""Recovery / regression dynamics and the negative-transfer recommendation (arXiv:2608.05643, Appendix A.2-A.3, Eq. 6-9)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from learning_transfer import (
    DetectorConfig,
    FlipAssessmentConfig,
    TraceTransition,
    TransferObservation,
    assess_flips,
    flag_for_review,
    flip_rates,
    question_level_rates,
    score_transfer_pair,
)


def pairs(stay_correct: int, stay_wrong: int, recovered: int, regressed: int, depth: int = 1) -> list[TraceTransition]:
    """A population of traces judged before and after one step."""
    rows: list[TraceTransition] = []
    for kind, count, before, after in (("cc", stay_correct, True, True), ("ww", stay_wrong, False, False), ("wc", recovered, False, True), ("cw", regressed, True, False)):
        rows += [TraceTransition(f"{kind}{i}", before, after, depth) for i in range(count)]
    return rows


# ---------------------------------------------------------------------------------------------- Eq. (8)-(9): trace-level flips

def test_flip_rates_and_net_correction_benefit() -> None:
    rates = flip_rates(pairs(stay_correct=40, stay_wrong=43, recovered=12, regressed=5))
    assert rates.pairs == 100 and (rates.wrong_to_correct, rates.correct_to_wrong) == (12, 5)
    assert rates.mu_wrong_to_correct == pytest.approx(0.12) and rates.mu_correct_to_wrong == pytest.approx(0.05)
    assert rates.net_benefit == pytest.approx(0.07), "B(d) = mu_{W->C} - mu_{C->W}"


def test_flip_rates_can_be_taken_per_depth() -> None:
    rows = pairs(10, 10, 4, 0, depth=1) + pairs(10, 10, 0, 4, depth=2)
    assert flip_rates(rows, depth=1).net_benefit > 0 > flip_rates(rows, depth=2).net_benefit
    assert flip_rates(rows).net_benefit == pytest.approx(0.0), "over all depths the two cancel"
    assert flip_rates([]).pairs == 0 and flip_rates([]).net_benefit == 0.0


# ----------------------------------------------------------------------------------------- Eq. (6)-(7): question-level flips

def test_question_level_rates_explain_the_accuracy_change() -> None:
    # delta(0), delta(1), delta(2) for six questions
    table = [
        [False, True, True],    # recovered at depth 1
        [False, False, True],   # recovered at depth 2
        [True, True, False],    # regressed at depth 2
        [True, True, True],
        [False, False, False],
        [False, True, False],   # recovered at 1, regressed at 2
    ]
    first, second = question_level_rates(table)
    assert first.recovery == pytest.approx(2 / 6) and first.regression == 0.0
    assert second.recovery == pytest.approx(1 / 6) and second.regression == pytest.approx(2 / 6)
    for entry in (first, second):
        assert entry.delta_accuracy == pytest.approx(entry.recovery - entry.regression), "dA(d) = rho_rec(d) - rho_reg(d)"
    assert first.accuracy == pytest.approx(4 / 6) and second.accuracy == pytest.approx(3 / 6)


def test_question_level_rates_need_a_rectangular_table() -> None:
    assert question_level_rates([]) == []
    with pytest.raises(ValueError):
        question_level_rates([[True, False], [True]])
    with pytest.raises(ValueError):
        question_level_rates([[True]])


def test_a_trace_level_regression_need_not_reach_the_final_answer() -> None:
    """The paper's caveat in numbers: 2 of 8 rollouts regress, yet the majority stays right, so rho_reg stays 0."""
    traces = pairs(stay_correct=4, stay_wrong=0, recovered=0, regressed=2) + pairs(0, 2, 0, 0)
    assert flip_rates(traces).mu_correct_to_wrong == pytest.approx(2 / 8)
    # six of eight rollouts are still right after the step, so the plurality answer is correct before and after
    final = question_level_rates([[True, True]])[0]
    assert final.regression == 0.0 and final.delta_accuracy == 0.0


# ------------------------------------------------------------------------------------------------ negative transfer verdicts

def test_net_benefit_below_zero_with_enough_data_is_flagged_negative_for_a_person_to_confirm() -> None:
    verdict = assess_flips(pairs(stay_correct=40, stay_wrong=30, recovered=5, regressed=25))
    assert verdict.rates.net_benefit < 0 and verdict.verdict == "negative"
    assert verdict.recommend_quarantine and verdict.requires_human_approval, "a recommendation, never an automatic rollback"
    assert verdict.p_harm is not None and verdict.p_harm < 0.001


def test_too_few_pairs_or_flips_is_not_enough_to_judge() -> None:
    few_pairs = assess_flips(pairs(5, 5, 0, 4))
    assert few_pairs.verdict == "insufficient_data" and not few_pairs.recommend_quarantine
    few_flips = assess_flips(pairs(60, 60, 1, 4))
    assert few_flips.verdict == "insufficient_data" and "5 flips" in few_flips.reason


def test_a_small_negative_balance_inside_the_noise_is_neutral() -> None:
    verdict = assess_flips(pairs(stay_correct=40, stay_wrong=40, recovered=7, regressed=9))
    assert verdict.rates.net_benefit < 0 and verdict.verdict == "neutral" and not verdict.recommend_quarantine
    assert verdict.p_harm is not None and verdict.p_harm > 0.05


def test_a_clear_positive_balance_is_positive() -> None:
    verdict = assess_flips(pairs(40, 30, 25, 5))
    assert verdict.verdict == "positive" and not verdict.recommend_quarantine


def test_trace_level_harm_that_the_final_answers_do_not_show_is_not_flagged() -> None:
    traces = pairs(stay_correct=40, stay_wrong=30, recovered=5, regressed=25)
    finals = pairs(stay_correct=18, stay_wrong=2, recovered=0, regressed=0)
    verdict = assess_flips(traces, final_outcomes=finals)
    assert verdict.verdict == "neutral" and not verdict.recommend_quarantine and "majority voting" in verdict.reason


def test_trace_level_harm_that_also_hurts_the_final_answers_is_flagged() -> None:
    traces = pairs(stay_correct=40, stay_wrong=30, recovered=5, regressed=25)
    finals = pairs(stay_correct=10, stay_wrong=2, recovered=1, regressed=5)
    assert assess_flips(traces, final_outcomes=finals).verdict == "negative"


def test_the_sign_test_is_exact() -> None:
    verdict = assess_flips(pairs(0, 0, 0, 8), FlipAssessmentConfig(minimum_pairs=8, minimum_discordant=8))
    assert verdict.p_harm == pytest.approx(1 / 256), "8 of 8 flips against the step: P(X >= 8) = 2^-8"
    assert verdict.verdict == "negative"


def test_assessment_settings_are_validated() -> None:
    with pytest.raises(ValueError):
        FlipAssessmentConfig(alpha=0.0)
    with pytest.raises(ValueError):
        FlipAssessmentConfig(minimum_pairs=0)


# ------------------------------------------------------------------------------- combined with the existing impact score

def observations(successes: int, failures: int) -> tuple[TransferObservation, ...]:
    return tuple(TransferObservation(True, 0, False, 100) for _ in range(successes)) + tuple(TransferObservation(False, 3, True, 100) for _ in range(failures))


def test_a_capsule_goes_to_review_when_either_signal_is_negative() -> None:
    capsule = uuid4()
    healthy = score_transfer_pair(capsule, "agent", observations(10, 0), observations(10, 0), DetectorConfig())
    harmful = score_transfer_pair(capsule, "agent", observations(10, 0), observations(2, 8), DetectorConfig())
    calm = assess_flips(pairs(40, 40, 7, 9))
    alarmed = assess_flips(pairs(40, 30, 5, 25))
    assert not flag_for_review(healthy, calm)
    assert flag_for_review(harmful, calm), "the existing impact score alone is enough"
    assert flag_for_review(healthy, alarmed), "so is the flip test alone"
