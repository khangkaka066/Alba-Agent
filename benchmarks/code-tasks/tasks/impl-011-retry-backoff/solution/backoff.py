def backoff_delays(
    max_retries: int,
    base: float,
    factor: float = 2.0,
    max_delay: float | None = None,
    budget: float | None = None,
) -> list[float]:
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    if base < 0:
        raise ValueError("base must be >= 0")
    if factor < 1:
        raise ValueError("factor must be >= 1")
    if max_delay is not None and max_delay < 0:
        raise ValueError("max_delay must be >= 0")
    if budget is not None and budget < 0:
        raise ValueError("budget must be >= 0")
    delays: list[float] = []
    spent = 0.0
    for i in range(max_retries):
        delay = float(base * factor**i)
        if max_delay is not None:
            delay = min(delay, float(max_delay))
        if budget is not None and spent + delay > budget:
            break
        spent += delay
        delays.append(delay)
    return delays


def total_wait(delays: list[float]) -> float:
    total = 0.0
    for d in delays:
        total += d
    return total
