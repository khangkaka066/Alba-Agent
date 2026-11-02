"""Concurrent draft, cross-examination and arbitration primitives."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence


@dataclass(frozen=True)
class ModelDraft:
    model: str
    output: str


@dataclass(frozen=True)
class ConsensusResult:
    output: str
    consensus_confidence: float
    dissent_report: str
    drafts: tuple[ModelDraft, ...]
    approval_required: bool


Executor = Callable[[str], Awaitable[str]]
Critic = Callable[[ModelDraft, ModelDraft], Awaitable[str]]
Arbiter = Callable[[Sequence[ModelDraft], Sequence[str]], Awaitable[tuple[str, float]]]


class ConsensusEngine:
    def __init__(self, executor: Executor, critic: Critic, arbiter: Arbiter) -> None:
        self._executor, self._critic, self._arbiter = executor, critic, arbiter

    async def run(self, models: Sequence[str], threshold: float) -> ConsensusResult:
        if len(models) < 2 or not 0 <= threshold <= 1:
            raise ValueError("Consensus requires two models and a threshold in [0,1]")
        drafts = tuple(ModelDraft(model, output) for model, output in zip(
            models, await asyncio.gather(*(self._executor(model) for model in models)), strict=True
        ))
        critiques = await asyncio.gather(*(
            self._critic(left, right) for index, left in enumerate(drafts)
            for right in drafts[index + 1:]
        ))
        output, confidence = await self._arbiter(drafts, critiques)
        if not 0 <= confidence <= 1:
            raise ValueError("Arbiter confidence must be in [0,1]")
        report = "\n".join(f"{draft.model}: {critique}" for draft, critique in zip(drafts, critiques))
        return ConsensusResult(output, confidence, report, drafts, confidence < threshold)
