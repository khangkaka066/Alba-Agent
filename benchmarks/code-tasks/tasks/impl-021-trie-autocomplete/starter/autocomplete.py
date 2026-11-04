from __future__ import annotations


class Autocomplete:
    def __init__(self) -> None:
        raise NotImplementedError

    def add(self, word: str, weight: int = 1) -> None:
        raise NotImplementedError

    def remove(self, word: str) -> bool:
        raise NotImplementedError

    def weight_of(self, word: str) -> int:
        raise NotImplementedError

    def suggest(self, prefix: str, limit: int = 5) -> list[str]:
        raise NotImplementedError

    def count_prefix(self, prefix: str) -> int:
        raise NotImplementedError

    def __contains__(self, word: object) -> bool:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError
