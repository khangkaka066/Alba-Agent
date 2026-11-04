from __future__ import annotations

from typing import Any


class PathSyntaxError(ValueError):
    pass


def parse_path(path: str) -> list[str | int]:
    raise NotImplementedError


def get_path(data: Any, path: str, default: Any = None) -> Any:
    raise NotImplementedError


def has_path(data: Any, path: str) -> bool:
    raise NotImplementedError
