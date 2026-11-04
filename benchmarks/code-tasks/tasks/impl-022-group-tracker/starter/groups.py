from __future__ import annotations

from typing import Hashable


class GroupTracker:
    def __init__(self) -> None:
        raise NotImplementedError

    def add(self, x: Hashable) -> None:
        raise NotImplementedError

    def union(self, a: Hashable, b: Hashable) -> bool:
        raise NotImplementedError

    def connected(self, a: Hashable, b: Hashable) -> bool:
        raise NotImplementedError

    def size_of(self, x: Hashable) -> int:
        raise NotImplementedError

    def members(self, x: Hashable) -> list:
        raise NotImplementedError

    @property
    def group_count(self) -> int:
        raise NotImplementedError

    def groups(self) -> list[list]:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __contains__(self, x: object) -> bool:
        raise NotImplementedError
