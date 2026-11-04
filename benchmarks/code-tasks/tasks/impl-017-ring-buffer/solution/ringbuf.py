from __future__ import annotations

from typing import Any, Iterator


class RingBuffer:
    def __init__(self, capacity: int) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be an int >= 1")
        self._capacity = capacity
        self._slots: list[Any] = [None] * capacity
        self._start = 0
        self._size = 0
        self._dropped = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def dropped(self) -> int:
        return self._dropped

    def push(self, item: Any) -> bool:
        if self._size == self._capacity:
            self._slots[self._start] = item
            self._start = (self._start + 1) % self._capacity
            self._dropped += 1
            return True
        self._slots[(self._start + self._size) % self._capacity] = item
        self._size += 1
        return False

    def pop_oldest(self) -> Any:
        if self._size == 0:
            raise IndexError("buffer is empty")
        item = self._slots[self._start]
        self._slots[self._start] = None
        self._start = (self._start + 1) % self._capacity
        self._size -= 1
        return item

    def peek_oldest(self) -> Any:
        return self[0]

    def peek_newest(self) -> Any:
        return self[-1]

    def is_full(self) -> bool:
        return self._size == self._capacity

    def latest(self, n: int) -> list[Any]:
        if n < 0:
            raise ValueError("n must be >= 0")
        items = self.to_list()
        return items[len(items) - min(n, len(items)):]

    def to_list(self) -> list[Any]:
        return [self._slots[(self._start + i) % self._capacity] for i in range(self._size)]

    def clear(self) -> None:
        self._slots = [None] * self._capacity
        self._start = 0
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def __getitem__(self, index: int) -> Any:
        if not -self._size <= index < self._size:
            raise IndexError("index out of range")
        if index < 0:
            index += self._size
        return self._slots[(self._start + index) % self._capacity]

    def __iter__(self) -> Iterator[Any]:
        return iter(self.to_list())
