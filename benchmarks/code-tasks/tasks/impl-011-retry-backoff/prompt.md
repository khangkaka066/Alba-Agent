Implement `backoff_delays` and `total_wait` in `backoff.py`.

`backoff_delays(max_retries: int, base: float, factor: float = 2.0, max_delay: float | None = None, budget: float | None = None) -> list[float]`
returns the planned wait (in seconds) before each retry, in order. It does not sleep and uses no randomness.
- The delay before retry number `i` (`i = 0, 1, 2, ...`) is `base * factor ** i`.
- If `max_delay` is not `None`, every delay is capped: `min(delay, max_delay)`.
- The list normally has exactly `max_retries` entries; `max_retries == 0` gives `[]`.
- If `budget` is not `None`, it is a limit on the SUM of all delays. Build the list in order and stop at the first delay that would push the running total strictly above `budget`; that delay and all later ones are omitted. A running total exactly equal to `budget` is allowed. (So the result may be shorter than `max_retries`, or empty.)
- Validation, raising `ValueError`: `max_retries < 0`, `base < 0`, `factor < 1`, `max_delay is not None and max_delay < 0`, `budget is not None and budget < 0`.
- Return plain `float` values (e.g. `[1.0, 2.0, 4.0]` for `base=1`, not ints).

`total_wait(delays: list[float]) -> float`
- Sum of the delays as a float; `0.0` for an empty list.
