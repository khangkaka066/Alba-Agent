from __future__ import annotations

from collections import deque
from typing import Callable


class WindowStats:
    def __init__(self, window_seconds: float, clock: Callable[[], float]) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._window = window_seconds
        self._clock = clock
        self._samples: deque[tuple[float, float]] = deque()

    def add(self, value: float) -> None:
        now = self._clock()
        self._evict(now)
        self._samples.append((now, value))

    def _evict(self, now: float) -> None:
        while self._samples and now - self._samples[0][0] >= self._window:
            self._samples.popleft()

    def _values(self) -> list[float]:
        self._evict(self._clock())
        return [v for _, v in self._samples]

    def count(self) -> int:
        return len(self._values())

    def total(self) -> float:
        return sum(self._values())

    def mean(self) -> float | None:
        values = self._values()
        return sum(values) / len(values) if values else None

    def minimum(self) -> float | None:
        values = self._values()
        return min(values) if values else None

    def maximum(self) -> float | None:
        values = self._values()
        return max(values) if values else None

    def rate_per_second(self) -> float:
        return self.count() / self._window

    def snapshot(self) -> dict:
        values = self._values()
        return {
            "count": len(values),
            "total": sum(values),
            "mean": sum(values) / len(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
