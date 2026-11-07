"""Breadth-depth refinement (arXiv:2608.05643, Algorithm 1) with scripted policies: no model, no network.

Each test pins one claim: the three-stage order and what each stage is conditioned on, the mandatory critique, the cluster entropy
H(N), early stopping on U(d) = 1, plurality voting, open-ended selection, redundancy handling, the call budget and the flip counts.
"""

from __future__ import annotations

import asyncio
import itertools
import math
from collections.abc import Sequence
from typing import Any, Literal, cast

import pytest

from consensus import (
    BreadthDepthRefiner,
    Critique,
    LexicalEmbedder,
    MissingCritiqueError,
    RefinerConfig,
    agglomerative_clusters,
    cluster_stats,
    cosine,
    planned_model_calls,
    plurality_vote,
    redundant_pairs,
)


def run(coroutine: Any) -> Any:
    return asyncio.run(coroutine)


# ---------------------------------------------------------------------------------------------------------------- stage order

def test_each_rollout_runs_generate_critique_correct_with_the_documented_conditioning() -> None:
    log: list[tuple[str, str | None, str | None]] = []
    temperatures: list[float] = []
    initial = iter(["t0", "t1"])

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        temperatures.append(temperature)
        log.append(("G", previous, None))
        return next(initial) if previous is None else f"g[{previous}]"

    async def critic(problem: str, draft: str) -> Critique:
        log.append(("C", draft, None))
        return Critique(f"checked {draft}", defects=1, pass_score=0.4)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        log.append(("R", draft, critique.text))
        return f"r[{draft}]"

    refiner = BreadthDepthRefiner(generate, critic, corrector, config=RefinerConfig(breadth=2, depth=2, early_stop=False))
    result = run(refiner.run("x"))

    assert [role for role, _, _ in log] == ["G", "G"] + ["G", "G", "C", "C", "R", "R"] * 2, "initial batch, then G/C/R as three batches per depth"
    assert result.model_calls == planned_model_calls(2, 2) == 14
    assert result.calls_by_role == {"generate": 6, "critique": 4, "correct": 4}
    assert temperatures == [0.7] * 6, "every generator call uses the fixed sampling temperature"
    depth1 = log[2:8]
    assert [previous for role, previous, _ in depth1 if role == "G"] == ["t0", "t1"], "g conditions on the previous corrected trace r^(d-1)"
    assert [draft for role, draft, _ in depth1 if role == "C"] == ["g[t0]", "g[t1]"], "the critic sees g, nothing else"
    assert [(draft, text) for role, draft, text in depth1 if role == "R"] == [("g[t0]", "checked g[t0]"), ("g[t1]", "checked g[t1]")], \
        "the corrector gets g AND its critique"
    depth2 = log[8:14]
    assert [previous for role, previous, _ in depth2 if role == "G"] == ["r[g[t0]]", "r[g[t1]]"], "depth 2 starts from the corrected trace"


def test_planned_calls_for_the_papers_setting() -> None:
    assert planned_model_calls(8, 4) == 104
    assert planned_model_calls(1, 1) == 4


# ------------------------------------------------------------------------------------------------------ mandatory critique

def test_a_critique_must_be_explicit_text() -> None:
    with pytest.raises(MissingCritiqueError):
        Critique("   ")
    with pytest.raises(ValueError):
        Critique("ok", defects=-1)
    with pytest.raises(ValueError):
        Critique("ok", pass_score=1.5)


def test_the_corrector_is_never_called_without_a_critique() -> None:
    corrected: list[str] = []

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return previous or "trace"

    async def silent_critic(problem: str, draft: str) -> Critique:
        return Critique("")  # no explicit critique: refinement must not go on to correct

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        corrected.append(draft)
        return "changed"

    result = run(BreadthDepthRefiner(generate, silent_critic, corrector, config=RefinerConfig(breadth=3, depth=2)).run("x"))
    assert corrected == []
    assert result.depths[0].failed == 3 and result.calls_by_role.get("correct", 0) == 0
    assert result.trace == "trace", "a rollout whose cycle failed keeps its previous trace"


def test_a_critic_that_returns_something_else_than_a_critique_blocks_the_correction() -> None:
    corrected: list[str] = []

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return previous or "trace"

    async def bad_critic(problem: str, draft: str) -> Critique:
        return cast(Critique, "looks fine")

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        corrected.append(draft)
        return draft

    run(BreadthDepthRefiner(generate, bad_critic, corrector, config=RefinerConfig(breadth=2, depth=1)).run("x"))
    assert corrected == []


# ------------------------------------------------------------------------------------------------- diversity and entropy H(N)

def unit(angle_degrees: float) -> list[float]:
    angle = math.radians(angle_degrees)
    return [math.cos(angle), math.sin(angle)]


def test_cluster_entropy_of_a_known_partition() -> None:
    e1, e2, e3 = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
    vectors = [e1, [0.99, 0.1, 0.0], [0.98, 0.0, 0.1], [0.97, 0.1, 0.1], e2, [0.1, 0.99, 0.0], e3, [0.0, 0.1, 0.99]]
    clusters = agglomerative_clusters(vectors, 0.85)
    assert clusters == [[0, 1, 2, 3], [4, 5], [6, 7]]
    stats = cluster_stats(clusters)
    assert stats.realised == 3 and stats.per_sample == pytest.approx(3 / 8) and stats.dominant_share == pytest.approx(0.5)
    assert stats.entropy_bits == pytest.approx(1.5), "H = -(0.5 log2 0.5 + 2 * 0.25 log2 0.25) = 1.5 bits"


def test_entropy_bounds_one_direction_and_all_distinct() -> None:
    same = cluster_stats(agglomerative_clusters([[1.0, 0.0]] * 5, 0.85))
    assert same.realised == 1 and same.entropy_bits == 0.0 and same.dominant_share == 1.0
    orthogonal = cluster_stats(agglomerative_clusters([[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]], 0.85))
    assert orthogonal.realised == 4 and orthogonal.entropy_bits == pytest.approx(2.0), "N distinct directions give log2 N bits"
    assert cluster_stats([]).entropy_bits == 0.0


def test_the_threshold_is_cosine_similarity_tau_sim() -> None:
    assert agglomerative_clusters([unit(0), unit(math.degrees(math.acos(0.86)))], 0.85) == [[0, 1]], "similarity 0.86 merges at 0.85"
    assert agglomerative_clusters([unit(0), unit(math.degrees(math.acos(0.84)))], 0.85) == [[0], [1]], "similarity 0.84 does not"


def test_average_linkage_does_not_chain_a_drifting_sequence() -> None:
    step = math.degrees(math.acos(0.9))
    vectors = [unit(0), unit(step), unit(2 * step)]  # 0-1 and 1-2 are 0.9 similar, 0-2 only about 0.62
    assert cosine(vectors[0], vectors[2]) < 0.7
    assert agglomerative_clusters(vectors, 0.85) == [[0, 1], [2]], "single linkage would give one chain; average linkage must not"


def test_a_zero_vector_has_no_direction() -> None:
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 0.0])


def test_redundant_pairs_need_the_same_cluster_and_a_higher_similarity() -> None:
    vectors = [unit(0), unit(10), unit(70)]
    clusters = agglomerative_clusters(vectors, 0.85)
    assert [(i, j) for i, j, _ in redundant_pairs(vectors, clusters, 0.92)] == [(0, 1)]
    assert redundant_pairs(vectors, clusters, 0.999) == []


# ----------------------------------------------------------------------------------------------------- early stop on U(d) = 1

def answer_of(trace: str) -> str | None:
    return trace.split("ans=")[1] if "ans=" in trace else None


def steady_policies(answers: Sequence[str], defects: int) -> tuple[Any, Any, Any]:
    pool = itertools.cycle(answers)

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return f"ans={next(pool)}" if previous is None else previous

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("confirmed" if defects == 0 else "found a flaw", defects=defects, pass_score=1.0 if defects == 0 else 0.3)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft

    return generate, critic, corrector


def test_it_stops_at_the_first_depth_where_all_answers_agree_and_no_defect_is_reported() -> None:
    result = run(BreadthDepthRefiner(*steady_policies(["42"], 0), extract=answer_of, config=RefinerConfig(breadth=4, depth=4)).run("x"))
    assert result.stopped_at == 1 and result.stopped_reason == "agreement"
    assert result.model_calls == 4 + 3 * 4, "the other three depths are not paid for"
    assert result.answer == "42" and result.method == "plurality" and result.depths[0].agreement


def test_it_goes_on_while_the_critic_still_reports_defects() -> None:
    result = run(BreadthDepthRefiner(*steady_policies(["42"], 2), extract=answer_of, config=RefinerConfig(breadth=4, depth=3)).run("x"))
    assert result.stopped_reason == "completed" and result.stopped_at == 3 and result.model_calls == planned_model_calls(4, 3)


def test_it_goes_on_while_the_rollouts_disagree() -> None:
    result = run(BreadthDepthRefiner(*steady_policies(["1", "2"], 0), extract=answer_of, config=RefinerConfig(breadth=4, depth=3)).run("x"))
    assert result.stopped_reason == "completed" and not result.depths[0].agreement and result.depths[0].distinct_answers == 2


def test_early_stopping_can_be_switched_off_and_needs_an_extractor() -> None:
    off = run(BreadthDepthRefiner(*steady_policies(["42"], 0), extract=answer_of, config=RefinerConfig(breadth=3, depth=2, early_stop=False)).run("x"))
    assert off.stopped_at == 2
    no_extractor = run(BreadthDepthRefiner(*steady_policies(["42"], 0), config=RefinerConfig(breadth=3, depth=2)).run("x"))
    assert no_extractor.stopped_at == 2, "without an answer extractor there is no agreement to measure"


# ------------------------------------------------------------------------------------------------------------ plurality vote

def test_plurality_vote_counts_non_empty_answers() -> None:
    assert plurality_vote(["a", "b", "a", None]) == ("a", {"a": 2, "b": 1})
    assert plurality_vote([None, None]) == (None, {})


def test_a_tie_goes_to_the_better_self_critique_then_to_the_earlier_rollout() -> None:
    assert plurality_vote(["a", "b", "b", "a"], [0.1, 0.9, 0.8, 0.2])[0] == "b"
    assert plurality_vote(["a", "b"], [0.5, 0.5])[0] == "a"
    with pytest.raises(ValueError):
        plurality_vote(["a"], [0.1, 0.2])


def test_the_returned_trace_is_the_best_critiqued_supporter_of_the_winner() -> None:
    scores = {"ans=7 weak": 0.2, "ans=7 strong": 0.9, "ans=8 other": 0.99}
    texts = iter(["ans=7 weak", "ans=7 strong", "ans=8 other"])

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return next(texts) if previous is None else previous

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1, pass_score=scores[draft])

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft

    def first_token(trace: str) -> str | None:
        return trace.split("ans=")[1].split()[0]

    result = run(BreadthDepthRefiner(generate, critic, corrector, extract=first_token, config=RefinerConfig(breadth=3, depth=1)).run("x"))
    assert result.answer == "7" and result.trace == "ans=7 strong" and result.vote_tally == {"7": 2, "8": 1}


# --------------------------------------------------------------------------------------------------- open-ended artifacts

class KeywordEmbedder:
    """Maps a text to a direction by the first keyword it contains, so clusters are exact and deterministic.

    A text with no keyword (the problem statement, which is embedded along with the rollouts) gets the zero vector: no direction.
    """

    name = "keyword"

    def __init__(self, directions: dict[str, list[float]]) -> None:
        self._directions = directions
        self._none = [0.0] * len(next(iter(directions.values())))

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [next((v for key, v in self._directions.items() if key in text), self._none) for text in texts]


def test_open_ended_output_takes_the_best_critiqued_trace_of_the_dominant_cluster() -> None:
    texts = iter(["quick A", "quick B", "quick C", "merge D", "merge E"])
    scores = {"quick A": 0.5, "quick B": 0.8, "quick C": 0.6, "merge D": 0.99, "merge E": 0.9}

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return next(texts) if previous is None else previous

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1, pass_score=scores[draft])

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft

    embedder = KeywordEmbedder({"quick": [1.0, 0.0, 0.0], "merge": [0.0, 1.0, 0.0]})
    result = run(BreadthDepthRefiner(generate, critic, corrector, embedder=embedder, config=RefinerConfig(breadth=5, depth=1)).run("x"))
    assert result.method == "dominant_cluster"
    assert result.trace == "quick B", "the larger cluster wins even though a merge-sort trace has the highest score"
    assert result.terminal_diverse


# ------------------------------------------------------------------------------------------------------------ redundancy

def duplicate_setup() -> tuple[Any, Any, Any, list[str | None], KeywordEmbedder]:
    hints: list[str | None] = []
    texts = iter(["alpha 1", "alpha 2", "beta 3", "gamma 4"])

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        hints.append(hint)
        if previous is not None:
            return previous
        return f"delta {len(hints)}" if hint else next(texts)

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1, pass_score=0.5)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft

    embedder = KeywordEmbedder({"alpha": [1.0, 0.0, 0.0, 0.0], "beta": [0.0, 1.0, 0.0, 0.0], "gamma": [0.0, 0.0, 1.0, 0.0], "delta": [0.0, 0.0, 0.0, 1.0]})
    return generate, critic, corrector, hints, embedder


def test_redundant_rollouts_are_reported_but_left_alone_by_default() -> None:
    generate, critic, corrector, hints, embedder = duplicate_setup()
    result = run(BreadthDepthRefiner(generate, critic, corrector, embedder=embedder, config=RefinerConfig(breadth=4, depth=1)).run("x"))
    assert [(i, j) for i, j, _ in result.redundant_pairs] == [(0, 1)] and result.injected == () and result.pruned == ()
    assert result.initial_diversity is not None and result.initial_diversity.realised == 3 and result.rollouts == 4
    assert result.initial_diversity.entropy_bits == pytest.approx(1.5)


def test_pruning_drops_the_later_duplicate() -> None:
    generate, critic, corrector, _, embedder = duplicate_setup()
    config = RefinerConfig(breadth=4, depth=1, redundancy_action="prune")
    result = run(BreadthDepthRefiner(generate, critic, corrector, embedder=embedder, config=config).run("x"))
    assert result.pruned == (1,) and result.rollouts == 3
    assert result.model_calls == 4 + 3 * 3, "a pruned rollout is not refined, so it is not paid for"


def test_injection_regenerates_the_duplicate_under_a_different_approach_constraint() -> None:
    generate, critic, corrector, hints, embedder = duplicate_setup()
    config = RefinerConfig(breadth=4, depth=1, redundancy_action="inject")
    result = run(BreadthDepthRefiner(generate, critic, corrector, embedder=embedder, config=config).run("x"))
    assert result.injected == (1,) and result.rollouts == 4
    constrained = [hint for hint in hints if hint]
    assert len(constrained) == 1 and "different approach" in constrained[0] and "alpha 1" in constrained[0]


# -------------------------------------------------------------------------------------------------------------------- budget

def test_the_call_budget_is_checked_before_each_depth() -> None:
    config = RefinerConfig(breadth=4, depth=3, max_model_calls=20, early_stop=False)
    result = run(BreadthDepthRefiner(*steady_policies(["1"], 1), extract=answer_of, config=config).run("x"))
    assert result.stopped_reason == "budget" and result.stopped_at == 1 and result.model_calls == 16 <= 20
    assert result.answer == "1", "what was reached is still aggregated"


def test_a_budget_below_the_breadth_is_rejected() -> None:
    with pytest.raises(ValueError):
        RefinerConfig(breadth=8, max_model_calls=7)


@pytest.mark.parametrize("kwargs", [{"breadth": 0}, {"depth": 0}, {"temperature": 0.0}, {"tau_sim": 1.2}, {"max_concurrency": 0}])
def test_invalid_configuration_is_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        RefinerConfig(**kwargs)


# ------------------------------------------------------------------------------------------------- recovery / regression flips

def test_flips_between_wrong_and_correct_are_counted_per_depth() -> None:
    initial = iter(["bad", "bad", "good", "good"])

    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return next(initial) if previous is None else previous

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1, pass_score=0.5)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        # the first "bad" is repaired, the last "good" is corrupted, the others stay as they are
        return {"bad": "bad", "good": "good"}[draft]

    seen = {"flip": 0}

    async def flipping_corrector(problem: str, draft: str, critique: Critique) -> str:
        seen["flip"] += 1
        if seen["flip"] == 1:
            return "good"
        if seen["flip"] == 4:
            return "bad"
        return await corrector(problem, draft, critique)

    async def oracle(trace: str) -> bool | None:
        return trace == "good"

    result = run(BreadthDepthRefiner(generate, critic, flipping_corrector, oracle=oracle, config=RefinerConfig(breadth=4, depth=1)).run("x"))
    depth = result.depths[0]
    assert (depth.wrong_to_correct, depth.correct_to_wrong, depth.judged) == (1, 1, 4)


def test_an_unknown_verdict_is_not_counted_either_way() -> None:
    async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        return previous or "t"

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft + "!"

    async def oracle(trace: str) -> bool | None:
        return None

    result = run(BreadthDepthRefiner(generate, critic, corrector, oracle=oracle, config=RefinerConfig(breadth=2, depth=1)).run("x"))
    assert (result.depths[0].judged, result.depths[0].vote_correct) == (0, None)


# ------------------------------------------------------------------------------------------------------------ failure handling

def test_failed_initial_rollouts_are_dropped_and_total_failure_is_an_error() -> None:
    calls = itertools.count()

    async def flaky(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        if previous is None and next(calls) == 0:
            raise TimeoutError("first rollout")
        return previous or "ok"

    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft

    result = run(BreadthDepthRefiner(flaky, critic, corrector, config=RefinerConfig(breadth=3, depth=1)).run("x"))
    assert result.rollouts == 2 and any("dropped" in warning for warning in result.warnings)

    async def broken(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
        raise TimeoutError("down")

    with pytest.raises(RuntimeError):
        run(BreadthDepthRefiner(broken, critic, corrector, config=RefinerConfig(breadth=2, depth=1)).run("x"))


def test_an_embedder_outage_does_not_lose_the_rollouts() -> None:
    class Down:
        name = "down"

        async def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise ConnectionError("embedding service")

    result = run(BreadthDepthRefiner(*steady_policies(["5"], 1), extract=answer_of, embedder=Down(), config=RefinerConfig(breadth=3, depth=1)).run("x"))
    assert result.answer == "5" and result.initial_diversity is None and any("embedder failed" in w for w in result.warnings)


# ------------------------------------------------------------------------------------------------------ lexical embedder

def test_the_lexical_embedder_is_deterministic_unit_length_and_ranks_a_paraphrase_above_another_method() -> None:
    texts = [
        "Sort the list with quicksort: pick a pivot, partition the elements around it, then recurse on both halves.",
        "Quicksort the array by choosing a pivot value and partitioning the elements around it, recursing on each half.",
        "Use merge sort: split the list in two, sort each half recursively, and merge the two sorted halves together.",
    ]
    embedder = LexicalEmbedder()
    first, second = embedder.embed_sync(texts), embedder.embed_sync(texts)
    assert first == second
    assert all(math.isclose(sum(v * v for v in vector), 1.0) for vector in first)
    assert cosine(first[0], first[1]) > cosine(first[0], first[2]), "only the ORDER is promised: a bag of words separates methods narrowly"
    assert run(embedder.embed([""])) == [[0.0] * 2048], "empty text is a zero vector, not an error"


# --------------------------------------------------------------------------------------------- MiniLM through onnxruntime

def test_the_minilm_embedder_says_clearly_when_its_files_are_missing(tmp_path: Any) -> None:
    from consensus import EmbedderUnavailableError, MiniLMOnnxEmbedder

    with pytest.raises(EmbedderUnavailableError, match="model.onnx and tokenizer.json"):
        MiniLMOnnxEmbedder(tmp_path)


def test_the_minilm_embedder_matches_pairs_with_a_known_relation() -> None:
    """Runs only where a model folder is given: NEXUS_MINILM_DIR=<folder with model.onnx and tokenizer.json>. Reference values
    (about 0.89 for the movie pair, near 0 for the cat) are the ones the sentence-transformers documentation shows for this model."""
    import os

    folder = os.environ.get("NEXUS_MINILM_DIR")
    if not folder:
        pytest.skip("NEXUS_MINILM_DIR is not set")
    from consensus import MiniLMOnnxEmbedder

    vectors = MiniLMOnnxEmbedder(folder).embed_sync(["The new movie is awesome", "The new movie is so great", "The cat sits outside"])
    assert len(vectors[0]) == 384 and math.isclose(sum(v * v for v in vectors[0]), 1.0, rel_tol=1e-4)
    assert cosine(vectors[0], vectors[1]) > 0.8 and cosine(vectors[0], vectors[2]) < 0.3


# ------------------------------------------------------------------------------ direction analysis: topic removed, then grouped

def topic_batch(per_group: Sequence[int], topic: float = 3.0, noise: float = 0.15) -> tuple[list[list[float]], list[int], list[float]]:
    """Rollouts of one problem: a strong shared topic + one orthogonal direction per approach + a little noise. Returns vectors, labels, topic."""
    import random

    rng = random.Random(4)
    dims = 12
    topic_vector = [topic if d == 0 else 0.0 for d in range(dims)]
    vectors: list[list[float]] = []
    labels: list[int] = []
    for group, size in enumerate(per_group):
        for _ in range(size):
            vector = list(topic_vector)
            vector[1 + group] += 1.0
            vectors.append([value + rng.uniform(-noise, noise) for value in vector])
            labels.append(group)
    return vectors, labels, topic_vector


def test_a_shared_topic_hides_the_directions_in_the_raw_view_and_not_after_centering() -> None:
    from consensus import analyze_directions

    vectors, labels, _ = topic_batch([3, 3, 2])
    assert cosine(vectors[0], vectors[3]) > 0.85, "different approaches still look alike because of the shared topic"
    raw = analyze_directions(vectors, view="raw")
    assert raw.view == "raw" and raw.stats.realised == 1, "the paper's 0.85 on the raw vectors merges everything here"
    centered = analyze_directions(vectors)
    assert centered.view == "centered" and centered.stats.realised == 3
    assert sorted(len(c) for c in centered.clusters) == [2, 3, 3]
    assert [sorted({labels[i] for i in cluster}) for cluster in centered.clusters] == [[0], [1], [2]], "each cluster is one approach"
    assert centered.stats.entropy_bits == pytest.approx(-(2 * 0.375 * math.log2(0.375) + 0.25 * math.log2(0.25)))


def test_the_problem_statements_direction_can_be_removed_first() -> None:
    from consensus import analyze_directions, remove_direction

    vectors, _, topic = topic_batch([3, 3, 2])
    stripped = remove_direction(vectors, topic)
    assert cosine(stripped[0], stripped[3]) < cosine(vectors[0], vectors[3]) - 0.5
    with_problem = analyze_directions(vectors, topic)
    assert with_problem.stats.realised == 3 and with_problem.relative_similarity is not None
    assert with_problem.relative_similarity < with_problem.mean_similarity, "similarity to the problem is subtracted"


def test_the_centered_cut_is_a_cosine_that_may_be_negative() -> None:
    from consensus import CENTERED_TAU, center

    assert CENTERED_TAU == -0.1
    vectors, _, _ = topic_batch([3, 3, 2])
    centered = center(vectors)
    assert agglomerative_clusters(centered, -0.1) == agglomerative_clusters(centered, 0.0), "the window around -0.1 is stable"
    assert len(agglomerative_clusters(centered, 0.9)) > 5, "a positive threshold this high shatters the three groups"
    with pytest.raises(ValueError):
        agglomerative_clusters(centered, -1.5)


def test_fewer_than_three_rollouts_cannot_be_centered_and_use_the_raw_view() -> None:
    from consensus import analyze_directions

    same = analyze_directions([[1.0, 0.0], [1.0, 0.0]])
    assert same.view == "raw" and same.stats.realised == 1, "two copies are not split just because centering makes two points opposite"
    apart = analyze_directions([[1.0, 0.0], [0.0, 1.0]])
    assert apart.stats.realised == 2
    assert analyze_directions([]).clusters == [] and analyze_directions([[1.0, 0.0]]).stats.realised == 1


def test_the_single_direction_check_is_off_unless_a_margin_is_given() -> None:
    from consensus import analyze_directions

    alike = [[1.0, 0.1 * i, 0.0] for i in range(4)]
    assert analyze_directions(alike).single_direction_likely is None
    flagged = analyze_directions(alike, flat_margin=0.9)
    assert flagged.single_direction_likely is True and flagged.clusters == [[0, 1, 2, 3]]
    vectors, _, _ = topic_batch([3, 3, 2])
    assert analyze_directions(vectors, flat_margin=0.99).single_direction_likely is False


class TopicEmbedder:
    """Keyword -> topic + approach direction, so the raw view cannot tell approaches apart but a centered one can."""

    name = "topic"

    def __init__(self) -> None:
        self._directions = {"alpha": 1, "beta": 2, "gamma": 3}

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vector = [3.0, 0.0, 0.0, 0.0]
            for key, dim in self._directions.items():
                if key in text:
                    vector[dim] += 1.0
            out.append(vector)
        return out


def test_the_refiner_groups_by_direction_with_the_centered_view_by_default() -> None:
    async def critic(problem: str, draft: str) -> Critique:
        return Critique("graded", defects=1)

    async def corrector(problem: str, draft: str, critique: Critique) -> str:
        return draft

    def build(view: Literal["centered", "raw"]) -> BreadthDepthRefiner:
        texts = iter(["alpha 1", "alpha 2", "beta 3", "beta 4", "gamma 5", "gamma 6"])

        async def generate(problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str:
            return next(texts) if previous is None else previous

        config = RefinerConfig(breadth=6, depth=1, diversity_view=view)
        return BreadthDepthRefiner(generate, critic, corrector, embedder=TopicEmbedder(), config=config)

    centered, raw = run(build("centered").run("x")), run(build("raw").run("x"))
    assert centered.diversity_view == "centered" and centered.initial_diversity is not None and centered.initial_diversity.realised == 3
    assert centered.initial_diversity.entropy_bits == pytest.approx(math.log2(3))
    assert raw.diversity_view == "raw" and raw.initial_diversity is not None and raw.initial_diversity.realised == 1


def test_a_lexical_embedder_is_flagged_as_unable_to_tell_approaches_apart() -> None:
    result = run(BreadthDepthRefiner(*steady_policies(["5"], 1), extract=answer_of, config=RefinerConfig(breadth=3, depth=1)).run("x"))
    assert any("approximate" in warning and "lexical-hash" in warning for warning in result.warnings)
    quiet = run(BreadthDepthRefiner(*steady_policies(["5"], 1), extract=answer_of, embedder=TopicEmbedder(), config=RefinerConfig(breadth=3, depth=1)).run("x"))
    assert not any("approximate" in warning for warning in quiet.warnings)


def test_the_new_settings_are_validated() -> None:
    with pytest.raises(ValueError):
        RefinerConfig(tau_centered=1.5)
    assert RefinerConfig().diversity_view == "centered" and RefinerConfig().tau_centered == -0.1


# --------------------------------------------------------------- quality on labelled solution approaches (needs a model folder)

def pairs(x: int) -> float:
    return x * (x - 1) / 2


def adjusted_rand(truth: Sequence[int], predicted: Sequence[int]) -> float:
    table: dict[tuple[int, int], int] = {}
    for t, p in zip(truth, predicted, strict=True):
        table[(t, p)] = table.get((t, p), 0) + 1
    cells = sum(pairs(v) for v in table.values())
    rows = sum(pairs(sum(v for (t, _), v in table.items() if t == k)) for k in set(truth))
    cols = sum(pairs(sum(v for (_, p), v in table.items() if p == k)) for k in set(predicted))
    expected = rows * cols / pairs(len(truth))
    peak = (rows + cols) / 2
    return 1.0 if peak == expected else (cells - expected) / (peak - expected)


def test_a_sentence_encoder_recovers_the_solution_approach_that_the_raw_view_cannot() -> None:
    """Needs NEXUS_MINILM_DIR (any all-MiniLM ONNX folder). Fixture: 3 problems x 3 approaches x 4 wordings, written by hand."""
    import json
    import os
    from pathlib import Path

    from consensus import OnnxSentenceEmbedder, analyze_directions

    folder = os.environ.get("NEXUS_MINILM_DIR")
    if not folder:
        pytest.skip("NEXUS_MINILM_DIR is not set")
    embedder = OnnxSentenceEmbedder(folder)
    data = json.loads((Path(__file__).parent / "fixtures" / "labelled_rollouts.json").read_text())
    scores_centered, raw_clusters = [], []
    for entry in data.values():
        texts: list[str] = []
        truth: list[int] = []
        for label, variants in enumerate(entry["approaches"].values()):
            texts += variants
            truth += [label] * len(variants)
        vectors = embedder.embed_sync([*texts, entry["problem"]])
        centered = analyze_directions(vectors[:-1], vectors[-1])
        labels = [0] * len(texts)
        for index, cluster in enumerate(centered.clusters):
            for member in cluster:
                labels[member] = index
        scores_centered.append(adjusted_rand(truth, labels))
        raw_clusters.append(analyze_directions(vectors[:-1], view="raw").stats.realised)
    assert sum(scores_centered) / len(scores_centered) > 0.3, scores_centered
    assert all(count == len(texts) for count in raw_clusters), "the paper's 0.85 on the raw vectors leaves every short rollout alone"
