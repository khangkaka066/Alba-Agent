from __future__ import annotations

from typing import Mapping


class ExprError(ValueError):
    pass


class ExprSyntaxError(ExprError):
    pass


class UndefinedNameError(ExprError):
    pass


def evaluate(expression: str, variables: Mapping[str, float] | None = None) -> float:
    raise NotImplementedError
