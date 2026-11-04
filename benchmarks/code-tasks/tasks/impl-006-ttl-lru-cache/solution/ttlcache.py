from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    def __init__(self, capacity: int, ttl: float, clock: Callable[[], float]) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if ttl <= 0:
            raise ValueError("ttl must be > 0")
        self._capacity = capacity
        self._ttl = ttl
        self._clock = clock
        self._data: OrderedDict[Any, tuple[Any, float]] = OrderedDict()

    def _purge(self) -> None:
        now = self._clock()
        for key in [k for k, (_, exp) in self._data.items() if now >= exp]:
            del self._data[key]

    def _live(self, key: Any) -> bool:
        item = self._data.get(key)
        if item is None:
            return False
        if self._clock() >= item[1]:
            del self._data[key]
            return False
        return True

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        life = self._ttl if ttl is None else ttl
        if life <= 0:
            raise ValueError("ttl must be > 0")
        self._data[key] = (value, self._clock() + life)
        self._data.move_to_end(key)
        if len(self._data) > self._capacity:
            self._purge()
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)

    def get(self, key: Any, default: Any = None) -> Any:
        if not self._live(key):
            return default
        self._data.move_to_end(key)
        return self._data[key][0]

    def peek(self, key: Any, default: Any = None) -> Any:
        return self._data[key][0] if self._live(key) else default

    def delete(self, key: Any) -> bool:
        if not self._live(key):
            return False
        del self._data[key]
        return True

    def __len__(self) -> int:
        self._purge()
        return len(self._data)

    def __contains__(self, key: Any) -> bool:
        return self._live(key)

    def keys(self) -> list:
        self._purge()
        return list(self._data)

    def clear(self) -> None:
        self._data.clear()
