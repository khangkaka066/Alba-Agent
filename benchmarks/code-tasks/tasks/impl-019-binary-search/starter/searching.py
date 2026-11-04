from typing import Callable, Sequence


def lower_bound(a: Sequence[float], x: float) -> int:
    raise NotImplementedError


def upper_bound(a: Sequence[float], x: float) -> int:
    raise NotImplementedError


def count_in_range(a: Sequence[float], lo: float, hi: float) -> int:
    raise NotImplementedError


def nearest(a: Sequence[float], x: float) -> float:
    raise NotImplementedError


def first_true(pred: Callable[[int], bool], lo: int, hi: int) -> int:
    raise NotImplementedError
