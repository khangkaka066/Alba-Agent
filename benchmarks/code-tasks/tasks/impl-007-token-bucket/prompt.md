Implement the class `TokenBucket` in `ratelimit.py`: a token-bucket rate limiter driven by an injected clock.

`TokenBucket(capacity: int, refill_rate: float, clock: Callable[[], float])`
- `capacity` (maximum tokens) must be >= 1 and `refill_rate` (tokens added per second) must be > 0, otherwise `ValueError`.
- `clock()` returns the current time in seconds as a float. Read it with a single call per operation; never use the real clock.
- The bucket starts full (`capacity` tokens) and its internal "last refill time" is the clock value at construction.

Refill rule (applied at the start of every `allow`, `available` and `retry_after` call): with `now = clock()`, add `max(0, now - last) * refill_rate` tokens, cap the total at `capacity`, then set `last = now`. If the clock moves backwards, no tokens are added but `last` still becomes `now`. Token counts are floats and are not rounded.

Methods
- `allow(cost: int = 1) -> bool`: refill, then if at least `cost` tokens are available, subtract `cost` and return `True`; otherwise return `False` and consume nothing. `cost` must satisfy `1 <= cost <= capacity`, otherwise `ValueError` (raised before anything else happens).
- `available() -> float`: refill, then return the current token count without consuming anything.
- `retry_after(cost: int = 1) -> float`: refill, then return how many seconds must pass until `cost` tokens will be available: `0.0` if they are available now, else `(cost - tokens) / refill_rate`. Same `cost` validation as `allow`. It does not consume tokens.
- `reset() -> None`: refill the bucket to `capacity` and set `last` to `clock()`.
