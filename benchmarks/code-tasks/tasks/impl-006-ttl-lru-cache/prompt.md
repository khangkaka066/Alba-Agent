Implement the class `TTLCache` in `ttlcache.py`: a bounded cache whose entries expire after a time-to-live and which evicts the least recently used entry when full. Time comes from an injected `clock` callable (returning a float number of seconds), never from the real clock.

`TTLCache(capacity: int, ttl: float, clock: Callable[[], float])`
- `capacity` must be >= 1 and `ttl` must be > 0, otherwise `ValueError`.
- `ttl` is the default lifetime of an entry.

An entry stored at time `t` with lifetime `L` is alive while `now < t + L` and expired once `now >= t + L` (an entry is already expired exactly at `t + L`). Expired entries behave as if they were absent everywhere below.

Methods
- `set(key, value, ttl: float | None = None) -> None`: stores the entry, using `ttl` as its lifetime if given (must be > 0, else `ValueError`; `None` means the default). Setting an existing key replaces its value and lifetime (the expiry restarts from now) and makes it the most recently used. If the cache then holds more than `capacity` entries, first drop every expired entry; if it still holds too many, drop least recently used entries until it fits.
- `get(key, default=None)`: returns the value of a live entry and marks it most recently used (this does NOT extend its lifetime). For a missing or expired key it returns `default` (an expired entry is removed).
- `peek(key, default=None)`: like `get` but does not change recency.
- `delete(key) -> bool`: removes the entry; returns `True` if a live entry was removed, `False` if the key was missing or already expired.
- `__len__`: the number of live entries.
- `__contains__(key)`: whether a live entry exists; does not change recency.
- `keys() -> list`: keys of live entries ordered from least recently used to most recently used.
- `clear() -> None`: removes everything.

Recency order starts at insertion; only `set` and `get` (when the key is live) mark an entry most recently used. A stored value may be `None`; `get` must still return it for a live key (use `in` or `peek` with a sentinel to tell the difference from "missing").
