For a request-latency dashboard we need rolling statistics over the last few seconds of samples. Implement the `WindowStats` class in `window.py`.

`WindowStats(window_seconds, clock)`:
- `window_seconds` is a number > 0, otherwise `ValueError` is raised.
- `clock` is a zero-argument callable returning the current time in seconds as a float. Never use the real time; only call `clock()`. Time never goes backwards.

`add(value)` records a numeric sample timestamped with the current `clock()` value.

A sample is **in the window** at time `now` when `now - timestamp < window_seconds` (strictly less: a sample that is exactly `window_seconds` old has already expired). Every query below must call `clock()` itself to get `now` and ignore (and may discard) expired samples; only samples currently in the window are considered:

- `count() -> int`
- `total()`: the sum of the values (`0` when empty).
- `mean() -> float | None`: `total / count`, or `None` when empty.
- `minimum()` / `maximum()`: the smallest / largest value, or `None` when empty.
- `rate_per_second() -> float`: `count / window_seconds`.
- `snapshot() -> dict`: `{"count": ..., "total": ..., "mean": ..., "min": ..., "max": ...}` with the same values the individual methods would return at that moment (a single `clock()` reading is fine).

Samples may be added with equal timestamps. Memory must stay bounded by the samples in the window (discard expired ones as time passes), and adding/querying must be efficient for windows holding many thousands of samples.
