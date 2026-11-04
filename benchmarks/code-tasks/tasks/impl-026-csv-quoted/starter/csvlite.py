from __future__ import annotations


def parse_csv(text: str, delimiter: str = ",") -> list[list[str]]:
    raise NotImplementedError


def to_csv(rows: list[list[str]], delimiter: str = ",") -> str:
    raise NotImplementedError
