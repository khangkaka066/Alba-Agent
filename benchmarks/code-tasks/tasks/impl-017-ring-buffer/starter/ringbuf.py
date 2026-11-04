from __future__ import annotations

from typing import Any, Iterator


class RingBuffer:
    def __init__(self, capacity: int) -> None:
        raise NotImplementedError

    @property
    def capacity(self) -> int:
        raise NotImplementedError

    @property
    def dropped(self) -> int:
        raise NotImplementedError

    def push(self, item: Any) -> bool:
        raise NotImplementedError

    def pop_oldest(self) -> Any:
        raise NotImplementedError

    def peek_oldest(self) -> Any:
        raise NotImplementedError

    def peek_newest(self) -> Any:
        raise NotImplementedError

    def is_full(self) -> bool:
        raise NotImplementedError

    def latest(self, n: int) -> list[Any]:
        raise NotImplementedError

    def to_list(self) -> list[Any]:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __getitem__(self, index: int) -> Any:
        raise NotImplementedError

    def __iter__(self) -> Iterator[Any]:
        raise NotImplementedError
