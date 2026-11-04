from __future__ import annotations

from collections import deque


class WindowLimiter:
    def __init__(self, limit: int, window: float) -> None:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be an int >= 1")
        if window <= 0:
            raise ValueError("window must be > 0")
        self._limit = limit
        self._window = window
        self._events: dict[str, deque[tuple[float, int]]] = {}
        self._last: dict[str, float] = {}

    def _check_time(self, key: str, now: float) -> None:
        if key in self._last and now < self._last[key]:
            raise ValueError("time went backwards")

    def _used(self, key: str, now: float) -> int:
        q = self._events.get(key)
        if not q:
            return 0
        return sum(c for t, c in q if t > now - self._window)

    def allow(self, key: str, now: float, cost: int = 1) -> bool:
        if not isinstance(cost, int) or cost < 1:
            raise ValueError("cost must be an int >= 1")
        self._check_time(key, now)
        self._last[key] = now
        q = self._events.setdefault(key, deque())
        while q and q[0][0] <= now - self._window:
            q.popleft()
        if cost > self._limit or sum(c for _, c in q) + cost > self._limit:
            if not q:
                del self._events[key]
            return False
        q.append((now, cost))
        return True

    def remaining(self, key: str, now: float) -> int:
        self._check_time(key, now)
        return self._limit - self._used(key, now)

    def retry_after(self, key: str, now: float, cost: int = 1) -> float | None:
        if not isinstance(cost, int) or cost < 1:
            raise ValueError("cost must be an int >= 1")
        self._check_time(key, now)
        if cost > self._limit:
            return None
        live = [(t, c) for t, c in self._events.get(key, ()) if t > now - self._window]
        used = sum(c for _, c in live)
        if used + cost <= self._limit:
            return 0
        for t, c in live:  # ascending time order
            used -= c
            if used + cost <= self._limit:
                return (t + self._window) - now
        return None  # unreachable
