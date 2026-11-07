"""Breadth-depth test-time refinement: Algorithm 1 of arXiv:2608.05643 (Bilal et al., 2026, "Refining Over Resampling").

Stage 1  Breadth. N rollouts are sampled independently from the generator policy at a fixed temperature (the paper: tau = 0.7).
Stage 2  Depth. For d = 1..D every active rollout goes through three role-conditioned stages, each run as one parallel batch:
             g = pi_G(x, r^(d-1))   continue / rewrite the previous corrected trace            (Eq. 3)
             c = pi_C(x, g)         an explicit natural-language critique of g                  (Eq. 4)
             r = pi_R(x, g, c)      the corrected trace, conditioned on both g and c            (Eq. 5)
         The critique is mandatory (Table 2 of the paper: it is what makes refinement work): the corrector is never called without one.
Stage 3  Aggregation. A deterministic extractor Phi turns each terminal trace into a normalised answer and a parameter-free plurality
         vote picks the result. There is no reward model, verifier or learned stopping policy in the paper.

Extensions of ours, not in the paper (each is switchable and labelled where it acts):
  * `early_stop`: stop at depth d when the answers all agree (U(d) = 1) AND the critic found no defect in a majority of rollouts.
    In the paper U(d) is only a diagnostic and full agreement "remains relatively rare", so this rarely triggers.
  * `redundancy_action` ("inject" / "prune"): rollouts whose embeddings are closer than `redundancy_threshold` (0.92) inside one
    cluster are regenerated under a "take a different approach" constraint, or dropped. Off by default.
  * Open-ended artifacts (code, reports) have no extractor: the dominant semantic cluster of the terminal traces is chosen and, in
    it, the trace with the best final self-critique score.
  * `max_model_calls`: a hard cap on model calls, checked before every stage. N rollouts at depth D cost N + 3 N D calls.

The policies are injected callables, so this module knows nothing about gateways, providers or prompts.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from .diversity import CENTERED_TAU, PAPER_TAU_SIM, ClusterStats, DirectionAnalysis, analyze_directions, redundant_pairs
from .embedders import Embedder, LexicalEmbedder


class MissingCritiqueError(ValueError):
    """A critique without an explicit natural-language statement of what was checked or what is wrong."""


@dataclass(frozen=True)
class Critique:
    """c_i^(d): the critic's verdict on one intermediate trace. `defects` is 0 when it confirms the trace."""

    text: str
    defects: int = 0
    pass_score: float = 1.0

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise MissingCritiqueError("An explicit critique in natural language is required before any correction")
        if self.defects < 0 or not 0 <= self.pass_score <= 1:
            raise ValueError("defects must be >= 0 and pass_score within [0, 1]")


class Generator(Protocol):
    async def __call__(self, problem: str, previous: str | None, *, temperature: float, hint: str | None = None) -> str: ...


class Critic(Protocol):
    async def __call__(self, problem: str, draft: str) -> Critique: ...


class Corrector(Protocol):
    async def __call__(self, problem: str, draft: str, critique: Critique) -> str: ...


Extractor = Callable[[str], str | None]
"""Phi: a trace -> its normalised answer, or None when it has none."""

Oracle = Callable[[str], Awaitable[bool | None]]
"""Is this trace correct? True / False, or None when unknown (a test run, an approval). Only used for the diagnostics."""

StopReason = Literal["completed", "agreement", "budget"]

T = TypeVar("T")


async def _limited(gate: asyncio.Semaphore, awaitable: Awaitable[T]) -> T:
    async with gate:
        return await awaitable


async def _batch(gate: asyncio.Semaphore, jobs: Sequence[tuple[int, Awaitable[T]]]) -> dict[int, T]:
    """Run the jobs in parallel (bounded); a job that raised is simply absent from the result."""
    results = await asyncio.gather(*(_limited(gate, job) for _, job in jobs), return_exceptions=True)
    done: dict[int, T] = {}
    for (index, _), item in zip(jobs, results, strict=True):
        if not isinstance(item, BaseException):
            done[index] = item
    return done


@dataclass(frozen=True)
class RefinerConfig:
    breadth: int = 8
    depth: int = 4
    temperature: float = 0.7
    diversity_view: Literal["centered", "raw"] = "centered"
    tau_centered: float = CENTERED_TAU
    tau_sim: float = PAPER_TAU_SIM
    flat_margin: float | None = None
    redundancy_threshold: float = 0.92
    redundancy_action: Literal["off", "inject", "prune"] = "off"
    early_stop: bool = True
    max_concurrency: int = 8
    max_model_calls: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.breadth <= 64 or not 1 <= self.depth <= 16:
            raise ValueError("breadth must be in 1..64 and depth in 1..16")
        if self.temperature <= 0:
            raise ValueError("The paper samples at a fixed temperature > 0; independent rollouts need randomness")
        if not 0 <= self.tau_sim <= 1 or not -1 <= self.tau_centered <= 1 or not 0 < self.redundancy_threshold <= 1:
            raise ValueError("tau_sim must be in [0, 1], tau_centered in [-1, 1] and redundancy_threshold in (0, 1]")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if self.max_model_calls is not None and self.max_model_calls < self.breadth:
            raise ValueError("max_model_calls cannot be below the breadth: the initial rollouts alone need that many calls")


def planned_model_calls(breadth: int, depth: int) -> int:
    """Calls of a full run: N initial rollouts plus three stages for each of the N rollouts at each of the D depths."""
    return breadth + 3 * breadth * depth


@dataclass(frozen=True)
class DepthRecord:
    """What one refinement depth did. `pre_answers` is Phi(g) and `answers` is Phi(r) for the rollouts that were active."""

    depth: int
    active: int
    failed: int
    pre_answers: tuple[str | None, ...]
    answers: tuple[str | None, ...]
    answer_changes: int
    distinct_answers: int
    agreement: bool
    zero_defect: int
    vote: str | None
    vote_correct: bool | None
    wrong_to_correct: int
    correct_to_wrong: int
    judged: int


@dataclass(frozen=True)
class RefinementResult:
    answer: str | None
    trace: str | None
    method: Literal["plurality", "dominant_cluster", "none"]
    vote_tally: dict[str, int]
    rollouts: int
    depths: tuple[DepthRecord, ...]
    stopped_at: int
    stopped_reason: StopReason
    model_calls: int
    calls_by_role: dict[str, int]
    initial_diversity: ClusterStats | None
    diversity_view: Literal["centered", "raw"] | None
    single_direction_likely: bool | None
    redundant_pairs: tuple[tuple[int, int, float], ...]
    injected: tuple[int, ...]
    pruned: tuple[int, ...]
    terminal_diverse: bool
    warnings: tuple[str, ...]


def plurality_vote(answers: Sequence[str | None], scores: Sequence[float] | None = None) -> tuple[str | None, dict[str, int]]:
    """V(.): the most frequent non-empty answer. Ties go to the answer with the higher mean score, then to the earliest rollout."""
    weights = list(scores) if scores is not None else [0.0] * len(answers)
    if len(weights) != len(answers):
        raise ValueError("scores must match answers")
    tally = Counter(answer for answer in answers if answer is not None)
    if not tally:
        return None, {}
    best = max(tally.values())
    leaders = [answer for answer, count in tally.items() if count == best]

    def rank(answer: str) -> tuple[float, int]:
        supporters = [index for index, item in enumerate(answers) if item == answer]
        return (-sum(weights[i] for i in supporters) / len(supporters), supporters[0])

    return min(leaders, key=rank), dict(tally)


class _Calls:
    def __init__(self) -> None:
        self.by_role: Counter[str] = Counter()

    def add(self, role: str, count: int = 1) -> None:
        self.by_role[role] += count

    @property
    def total(self) -> int:
        return sum(self.by_role.values())


class BreadthDepthRefiner:
    def __init__(
        self,
        generator: Generator,
        critic: Critic,
        corrector: Corrector,
        *,
        extract: Extractor | None = None,
        oracle: Oracle | None = None,
        embedder: Embedder | None = None,
        config: RefinerConfig | None = None,
    ) -> None:
        self._generator, self._critic, self._corrector = generator, critic, corrector
        self._extract, self._oracle = extract, oracle
        self._embedder: Embedder = embedder or LexicalEmbedder()
        self._config = config or RefinerConfig()

    async def run(self, problem: str) -> RefinementResult:
        config = self._config
        calls = _Calls()
        gate = asyncio.Semaphore(config.max_concurrency)
        warnings: list[str] = []

        async def sample(previous: str | None, hint: str | None, role: str = "generate") -> str:
            calls.add(role)
            return await self._generator(problem, previous, temperature=config.temperature, hint=hint)

        def affordable(extra: int) -> bool:
            return config.max_model_calls is None or calls.total + extra <= config.max_model_calls

        # Stage 1: breadth, N independent rollouts conditioned only on the problem.
        first = await asyncio.gather(*(_limited(gate, sample(None, None)) for _ in range(config.breadth)), return_exceptions=True)
        current: dict[int, str] = {index: item for index, item in enumerate(first) if isinstance(item, str)}
        if not current:
            failure = next((item for item in first if isinstance(item, BaseException)), None)
            raise RuntimeError("Every initial rollout failed") from failure
        if len(current) < config.breadth:
            warnings.append(f"{config.breadth - len(current)} initial rollout(s) failed and were dropped")

        initial, pairs, injected, pruned, view, flat = await self._check_diversity(problem, current, sample, gate, affordable, warnings)

        # Stage 2: depth, three role-conditioned stages per rollout, each a parallel batch.
        records: list[DepthRecord] = []
        final_critique: dict[int, Critique] = {}
        stopped_reason: StopReason = "completed"
        for depth in range(1, config.depth + 1):
            active = sorted(current)
            if not affordable(3 * len(active)):
                stopped_reason = "budget"
                break
            drafts = await _batch(gate, [(i, sample(current[i], None)) for i in active])
            critiques = await _batch(gate, [(i, self._critique(problem, drafts[i], calls)) for i in sorted(drafts)])
            fixed = await _batch(gate, [(i, self._correct(problem, drafts[i], critiques[i], calls)) for i in sorted(critiques)])
            for index, revised in fixed.items():
                current[index] = revised
                final_critique[index] = critiques[index]
            record = await self._record(depth, active, drafts, fixed, critiques, current, final_critique)
            records.append(record)
            if config.early_stop and self._extract is not None and record.agreement and record.zero_defect * 2 > record.active:
                stopped_reason = "agreement"
                break

        answer, trace, method, tally, diverse = await self._aggregate(problem, current, final_critique, warnings)
        return RefinementResult(
            answer=answer, trace=trace, method=method, vote_tally=tally, rollouts=len(current), depths=tuple(records),
            stopped_at=len(records), stopped_reason=stopped_reason, model_calls=calls.total, calls_by_role=dict(calls.by_role),
            initial_diversity=initial, diversity_view=view, single_direction_likely=flat, redundant_pairs=tuple(pairs), injected=tuple(injected), pruned=tuple(pruned),
            terminal_diverse=diverse, warnings=tuple(warnings),
        )

    async def _analyse(self, problem: str, traces: Sequence[str]) -> tuple[DirectionAnalysis, list[list[float]]]:
        """Embed the traces together with the problem statement (as the last item) and group them by direction."""
        vectors = await self._embedder.embed([*traces, problem])
        config = self._config
        analysis = analyze_directions(
            vectors[:-1], vectors[-1], view=config.diversity_view, tau_centered=config.tau_centered, tau_raw=config.tau_sim,
            flat_margin=config.flat_margin,
        )
        return analysis, vectors[:-1]

    async def _check_diversity(
        self,
        problem: str,
        current: dict[int, str],
        sample: Callable[[str | None, str | None, str], Awaitable[str]],
        gate: asyncio.Semaphore,
        affordable: Callable[[int], bool],
        warnings: list[str],
    ) -> tuple[ClusterStats | None, list[tuple[int, int, float]], list[int], list[int], Literal["centered", "raw"] | None, bool | None]:
        """Group the initial rollouts by direction; report H(N); optionally replace or drop near-duplicates (extension, off by default)."""
        if len(current) < 2:
            return None, [], [], [], None, None
        order = sorted(current)
        try:
            analysis, vectors = await self._analyse(problem, [current[i] for i in order])
        except Exception as error:  # an embedder outage must not lose the rollouts that were already paid for
            warnings.append(f"diversity check skipped: embedder failed ({type(error).__name__})")
            return None, [], [], [], None, None
        if not getattr(self._embedder, "reliable_for_diversity", True):
            warnings.append(f"diversity figures from the {self._embedder.name} embedder are approximate: it cannot tell solution approaches apart")
        stats = analysis.stats
        # Near-copies are judged on the vectors as they are: removing what rollouts share would make any two look different.
        pairs = [(order[i], order[j], similarity) for i, j, similarity in redundant_pairs(vectors, [list(range(len(order)))], self._config.redundancy_threshold)]
        view, flat = analysis.view, analysis.single_direction_likely
        action = self._config.redundancy_action
        if action == "off" or not pairs:
            return stats, pairs, [], [], view, flat
        duplicates: dict[int, int] = {}
        for kept, repeat, _ in pairs:
            if kept not in duplicates and repeat not in duplicates:
                duplicates[repeat] = kept
        if action == "prune":
            for repeat in duplicates:
                del current[repeat]
            return stats, pairs, [], sorted(duplicates), view, flat
        injected: list[int] = []
        for repeat, kept in sorted(duplicates.items()):
            if not affordable(1):
                warnings.append("redundant rollouts left as they were: the model-call budget is used up")
                break
            hint = f"Solve it by a clearly different approach from this one, which is already covered:\n{current[kept][:400]}"
            try:
                current[repeat] = await _limited(gate, sample(None, hint, "generate"))
            except Exception as error:
                warnings.append(f"could not regenerate rollout {repeat} ({type(error).__name__})")
                continue
            injected.append(repeat)
        return stats, pairs, injected, [], view, flat

    async def _critique(self, problem: str, draft: str, calls: _Calls) -> Critique:
        calls.add("critique")
        critique = await self._critic(problem, draft)
        if not isinstance(critique, Critique):
            raise MissingCritiqueError("The critic must return a Critique")
        return critique

    async def _correct(self, problem: str, draft: str, critique: Critique, calls: _Calls) -> str:
        calls.add("correct")
        return await self._corrector(problem, draft, critique)

    async def _record(
        self,
        depth: int,
        active: list[int],
        drafts: dict[int, str],
        fixed: dict[int, str],
        critiques: dict[int, Critique],
        current: dict[int, str],
        final_critique: dict[int, Critique],
    ) -> DepthRecord:
        extract = self._extract
        pre = tuple((extract(drafts[i]) if extract and i in drafts else None) for i in active)
        post = tuple((extract(current[i]) if extract else None) for i in active)
        changes = sum(1 for i in fixed if extract and extract(drafts[i]) != extract(fixed[i]))
        distinct = {answer for answer in post if answer is not None}
        scores = [final_critique[i].pass_score if i in final_critique else 0.0 for i in active]
        vote, _ = plurality_vote(post, scores)
        wrong_to_correct = correct_to_wrong = judged = 0
        vote_correct: bool | None = None
        if self._oracle is not None:
            before = await asyncio.gather(*(self._oracle(drafts[i]) for i in fixed), return_exceptions=True)
            after = await asyncio.gather(*(self._oracle(fixed[i]) for i in fixed), return_exceptions=True)
            for was, now in zip(before, after, strict=True):
                if isinstance(was, bool) and isinstance(now, bool):
                    judged += 1
                    wrong_to_correct += int(not was and now)
                    correct_to_wrong += int(was and not now)
            if vote is not None:
                winner = next(i for i, answer in zip(active, post, strict=True) if answer == vote)
                try:
                    verdict = await self._oracle(current[winner])
                except Exception:
                    verdict = None
                vote_correct = verdict if isinstance(verdict, bool) else None
        return DepthRecord(
            depth=depth, active=len(active), failed=len(active) - len(fixed), pre_answers=pre, answers=post, answer_changes=changes,
            distinct_answers=len(distinct), agreement=len(distinct) == 1, zero_defect=sum(1 for c in critiques.values() if c.defects == 0),
            vote=vote, vote_correct=vote_correct, wrong_to_correct=wrong_to_correct, correct_to_wrong=correct_to_wrong, judged=judged,
        )

    async def _aggregate(
        self,
        problem: str,
        current: dict[int, str],
        final_critique: dict[int, Critique],
        warnings: list[str],
    ) -> tuple[str | None, str | None, Literal["plurality", "dominant_cluster", "none"], dict[str, int], bool]:
        order = sorted(current)
        scores = [final_critique[i].pass_score if i in final_critique else 0.0 for i in order]
        answers = [self._extract(current[i]) if self._extract else None for i in order]
        winner, tally = plurality_vote(answers, scores)
        if winner is not None:
            supporters = [p for p, answer in enumerate(answers) if answer == winner]
            best = max(supporters, key=lambda p: (scores[p], -p))
            return winner, current[order[best]], "plurality", tally, len(tally) > 1
        # Open-ended: no extractable answer. Pick the dominant semantic cluster, then the best self-critique inside it.
        best_overall = max(range(len(order)), key=lambda p: (scores[p], -p))
        if len(order) == 1:
            return current[order[0]], current[order[0]], "dominant_cluster", {}, False
        try:
            analysis, _ = await self._analyse(problem, [current[i] for i in order])
        except Exception as error:
            warnings.append(f"cluster selection skipped: embedder failed ({type(error).__name__}); best-scored rollout used")
            return current[order[best_overall]], current[order[best_overall]], "dominant_cluster", {}, False
        clusters = analysis.clusters
        dominant = max(clusters, key=lambda members: (len(members), sum(scores[p] for p in members) / len(members), -members[0]))
        pick = max(dominant, key=lambda p: (scores[p], -p))
        return current[order[pick]], current[order[pick]], "dominant_cluster", {}, len(clusters) > 1

