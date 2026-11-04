from __future__ import annotations

import math


class ScoreError(ValueError):
    """Raised for a score outside 0..100 or NaN."""


def _validate(entries: list[tuple[str, float]]) -> None:
    for _name, score in entries:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError(f"score must be int or float, got {type(score).__name__}")
        if isinstance(score, float) and math.isnan(score):
            raise ScoreError("score is NaN")
        if score < 0 or score > 100:
            raise ScoreError(f"score out of range: {score!r}")


def rank_scores(entries: list[tuple[str, float]]) -> list[tuple[int, str, float]]:
    _validate(entries)
    # sorted() is stable, so entries whose score and folded name tie keep their input order
    ordered = sorted(entries, key=lambda e: (-e[1], e[0].casefold()))
    result: list[tuple[int, str, float]] = []
    rank = 0
    previous: float | None = None
    for position, (name, score) in enumerate(ordered, start=1):
        if previous is None or score != previous:
            rank = position
            previous = score
        result.append((rank, name, score))
    return result


def top_n(entries: list[tuple[str, float]], n: int) -> list[tuple[int, str, float]]:
    _validate(entries)
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n must be an int")
    if n < 0:
        raise ValueError("n must not be negative")
    return [row for row in rank_scores(entries) if row[0] <= n]
