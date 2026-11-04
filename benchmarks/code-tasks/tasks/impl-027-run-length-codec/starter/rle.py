from __future__ import annotations


def runs(text: str) -> list[tuple[str, int]]:
    raise NotImplementedError


def encode(text: str) -> str:
    raise NotImplementedError


def decode(data: str, max_length: int | None = None) -> str:
    raise NotImplementedError
