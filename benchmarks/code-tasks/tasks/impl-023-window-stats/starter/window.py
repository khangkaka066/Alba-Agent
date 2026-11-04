from __future__ import annotations

from typing import Callable


class WindowStats:
    def __init__(self, window_seconds: float, clock: Callable[[], float]) -> None:
        raise NotImplementedError

    def add(self, value: float) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError

    def total(self) -> float:
        raise NotImplementedError

    def mean(self) -> float | None:
        raise NotImplementedError

    def minimum(self) -> float | None:
        raise NotImplementedError

    def maximum(self) -> float | None:
        raise NotImplementedError

    def rate_per_second(self) -> float:
        raise NotImplementedError

    def snapshot(self) -> dict:
        raise NotImplementedError
