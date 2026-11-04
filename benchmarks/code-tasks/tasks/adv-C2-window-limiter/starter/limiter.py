from __future__ import annotations


class WindowLimiter:
    def __init__(self, limit: int, window: float) -> None:
        raise NotImplementedError

    def allow(self, key: str, now: float, cost: int = 1) -> bool:
        raise NotImplementedError

    def remaining(self, key: str, now: float) -> int:
        raise NotImplementedError

    def retry_after(self, key: str, now: float, cost: int = 1) -> float | None:
        raise NotImplementedError
