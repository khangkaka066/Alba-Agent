"""Memoizing decorator backed by ``LRUCache``."""

import functools

from lru import LRUCache

_MISSING = object()


def memoize(maxsize=128):
    """Cache a function's results by its arguments, keeping at most ``maxsize`` results.

    Results are cached whatever their value, including ``None`` and falsy values, so the
    function is not called again for the same arguments while the result is cached. The
    wrapper gets ``cache_info()`` returning ``{"hits", "misses", "size"}`` (a hit is a
    call answered from the cache) and ``cache`` (the underlying LRUCache).
    """

    def decorator(fn):
        cache = LRUCache(maxsize)
        stats = {"hits": 0, "misses": 0}

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            cached = cache.get(key, _MISSING)
            if cached is not _MISSING:
                stats["hits"] += 1
                return cached
            stats["misses"] += 1
            value = fn(*args, **kwargs)
            cache.put(key, value)
            return value

        wrapper.cache = cache
        wrapper.cache_info = lambda: {"hits": stats["hits"], "misses": stats["misses"], "size": len(cache)}
        return wrapper

    return decorator
