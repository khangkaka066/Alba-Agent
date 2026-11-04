from __future__ import annotations

from typing import Hashable


class GroupTracker:
    def __init__(self) -> None:
        self._parent: dict[Hashable, Hashable] = {}
        self._size: dict[Hashable, int] = {}
        self._groups = 0

    def add(self, x: Hashable) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._size[x] = 1
            self._groups += 1

    def _find(self, x: Hashable) -> Hashable:
        if x not in self._parent:
            raise KeyError(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: Hashable, b: Hashable) -> bool:
        self.add(a)
        self.add(b)
        ra, rb = self._find(a), self._find(b)
        if ra == rb:
            return False
        if self._size[ra] < self._size[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]
        self._groups -= 1
        return True

    def connected(self, a: Hashable, b: Hashable) -> bool:
        return self._find(a) == self._find(b)

    def size_of(self, x: Hashable) -> int:
        return self._size[self._find(x)]

    def members(self, x: Hashable) -> list:
        root = self._find(x)
        return sorted(e for e in self._parent if self._find(e) == root)

    @property
    def group_count(self) -> int:
        return self._groups

    def groups(self) -> list[list]:
        by_root: dict[Hashable, list] = {}
        for e in self._parent:
            by_root.setdefault(self._find(e), []).append(e)
        result = [sorted(g) for g in by_root.values()]
        result.sort(key=lambda g: g[0])
        return result

    def __len__(self) -> int:
        return len(self._parent)

    def __contains__(self, x: object) -> bool:
        return x in self._parent
