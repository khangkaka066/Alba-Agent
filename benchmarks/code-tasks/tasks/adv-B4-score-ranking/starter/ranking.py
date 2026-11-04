from __future__ import annotations


class ScoreError(ValueError):
    """Raised for a score outside 0..100 or NaN."""


def rank_scores(entries: list[tuple[str, float]]) -> list[tuple[int, str, float]]:
    raise NotImplementedError


def top_n(entries: list[tuple[str, float]], n: int) -> list[tuple[int, str, float]]:
    raise NotImplementedError
