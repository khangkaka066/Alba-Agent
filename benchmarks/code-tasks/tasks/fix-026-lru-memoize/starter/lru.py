"""Least-recently-used cache."""

from collections import OrderedDict


class LRUCache:
    """Fixed-capacity mapping that evicts the least recently used entry.

    An entry is "used" when it is read with ``get`` or written with ``put`` (including
    overwriting an existing key). ``peek``, ``in`` and ``len`` do not count as use.
    ``keys()`` lists keys from least to most recently used.
    """

    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data = OrderedDict()

    def get(self, key, default=None):
        """Return the value for ``key`` (marking it used) or ``default`` when absent."""
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def peek(self, key, default=None):
        """Like ``get`` but does not mark the entry as used."""
        return self._data.get(key, default)

    def put(self, key, value):
        """Store ``value``; returns the evicted ``(key, value)`` pair or None.

        When the cache is full and ``key`` is new, the least recently used entry is
        removed first.
        """
        if key in self._data:
            self._data[key] = value
            return None
        evicted = None
        if len(self._data) >= self.capacity:
            evicted = self._data.popitem(last=False)
        self._data[key] = value
        return evicted

    def keys(self):
        return list(self._data)

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)
