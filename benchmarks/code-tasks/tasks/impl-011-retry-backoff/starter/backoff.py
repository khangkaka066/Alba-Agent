def backoff_delays(
    max_retries: int,
    base: float,
    factor: float = 2.0,
    max_delay: float | None = None,
    budget: float | None = None,
) -> list[float]:
    raise NotImplementedError


def total_wait(delays: list[float]) -> float:
    raise NotImplementedError
