from __future__ import annotations


class _Node:
    __slots__ = ("children", "weight")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.weight = 0  # 0 means: not a word end


class Autocomplete:
    def __init__(self) -> None:
        self._root = _Node()
        self._size = 0

    def _find(self, prefix: str) -> _Node | None:
        node = self._root
        for ch in prefix:
            node = node.children.get(ch)  # type: ignore[assignment]
            if node is None:
                return None
        return node

    def add(self, word: str, weight: int = 1) -> None:
        if not isinstance(word, str) or not word:
            raise ValueError("word must be a non-empty string")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
            raise ValueError("weight must be an int >= 1")
        node = self._root
        for ch in word:
            node = node.children.setdefault(ch, _Node())
        if node.weight == 0:
            self._size += 1
        node.weight += weight

    def remove(self, word: str) -> bool:
        node = self._find(word) if word else None
        if node is None or node.weight == 0:
            return False
        node.weight = 0
        self._size -= 1
        return True

    def weight_of(self, word: str) -> int:
        node = self._find(word) if word else None
        if node is None or node.weight == 0:
            raise KeyError(word)
        return node.weight

    def _collect(self, prefix: str) -> list[tuple[int, str]]:
        start = self._find(prefix)
        found: list[tuple[int, str]] = []
        if start is None:
            return found
        stack = [(start, prefix)]
        while stack:
            node, text = stack.pop()
            if node.weight:
                found.append((node.weight, text))
            for ch, child in node.children.items():
                stack.append((child, text + ch))
        return found

    def suggest(self, prefix: str, limit: int = 5) -> list[str]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("limit must be an int >= 0")
        found = self._collect(prefix)
        found.sort(key=lambda item: (-item[0], item[1]))
        return [word for _, word in found[:limit]]

    def count_prefix(self, prefix: str) -> int:
        return len(self._collect(prefix))

    def __contains__(self, word: object) -> bool:
        if not isinstance(word, str) or not word:
            return False
        node = self._find(word)
        return node is not None and node.weight > 0

    def __len__(self) -> int:
        return self._size
