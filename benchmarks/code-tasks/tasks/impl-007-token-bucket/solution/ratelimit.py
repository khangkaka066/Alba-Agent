from typing import Callable


class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float, clock: Callable[[], float]) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if refill_rate <= 0:
            raise ValueError("refill_rate must be > 0")
        self._capacity = capacity
        self._rate = refill_rate
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(float(self._capacity), self._tokens + elapsed * self._rate)
        self._last = now

    def _check_cost(self, cost: int) -> None:
        if cost < 1 or cost > self._capacity:
            raise ValueError("cost must be between 1 and capacity")

    def allow(self, cost: int = 1) -> bool:
        self._check_cost(cost)
        self._refill()
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False

    def available(self) -> float:
        self._refill()
        return self._tokens

    def retry_after(self, cost: int = 1) -> float:
        self._check_cost(cost)
        self._refill()
        if self._tokens >= cost:
            return 0.0
        return (cost - self._tokens) / self._rate

    def reset(self) -> None:
        self._tokens = float(self._capacity)
        self._last = self._clock()
