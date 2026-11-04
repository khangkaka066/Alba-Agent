from typing import Callable


class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float, clock: Callable[[], float]) -> None:
        raise NotImplementedError

    def allow(self, cost: int = 1) -> bool:
        raise NotImplementedError

    def available(self) -> float:
        raise NotImplementedError

    def retry_after(self, cost: int = 1) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError
