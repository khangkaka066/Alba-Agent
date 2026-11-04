from __future__ import annotations

from typing import Iterable


def parse_version(text: str) -> tuple[int, int, int]:
    raise NotImplementedError


def satisfies(version: str, spec: str) -> bool:
    raise NotImplementedError


def max_satisfying(versions: Iterable[str], spec: str) -> str | None:
    raise NotImplementedError
