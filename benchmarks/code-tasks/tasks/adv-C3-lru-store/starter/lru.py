from __future__ import annotations

from collections import deque


class LRUStore:
    """Least-recently-used key/value store with a fixed capacity (>= 1).

    - put(k, v): inserts or overwrites; either way k becomes the most recently used key.
      Overwriting an existing key never evicts anything. Inserting a new key into a full
      store first evicts the least recently used key and calls on_evict(key, value) once.
    - get(k, default=None): returns the value and makes k the most recently used key.
    - peek(k, default=None): returns the value without changing the usage order.
    - delete(k) -> bool: removes k (no on_evict call); True if it existed.
    - pop_oldest(): removes and returns the (key, value) of the least recently used
      entry (no on_evict call); raises KeyError when empty.
    - keys(): keys from least to most recently used. len(store) is the number of entries.
    """

    def __init__(self, capacity, on_evict=None):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._cap = capacity
        self._on_evict = on_evict
        self._data = {}
        self._order = deque()  # usage log, oldest first

    def put(self, key, value):
        if key not in self._data and len(self._data) >= self._cap:
            self._evict()
        self._data[key] = value
        self._order.append(key)

    def get(self, key, default=None):
        if key not in self._data:
            return default
        self._order.append(key)
        return self._data[key]

    def peek(self, key, default=None):
        return self._data.get(key, default)

    def delete(self, key):
        if key in self._data:
            del self._data[key]
            return True
        return False

    def pop_oldest(self):
        if not self._data:
            raise KeyError("empty")
        key = self._order.popleft()
        while key not in self._data:
            key = self._order.popleft()
        return key, self._data.pop(key)

    def _evict(self):
        key = self._order.popleft()
        value = self._data.pop(key, None)
        if self._on_evict is not None:
            self._on_evict(key, value)

    def keys(self):
        seen = []
        for k in self._order:
            if k in self._data and k not in seen:
                seen.append(k)
        return seen

    def __len__(self):
        return len(self._data)
