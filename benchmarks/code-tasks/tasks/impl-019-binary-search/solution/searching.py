from typing import Callable, Sequence


def lower_bound(a: Sequence[float], x: float) -> int:
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def upper_bound(a: Sequence[float], x: float) -> int:
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def count_in_range(a: Sequence[float], lo: float, hi: float) -> int:
    if lo > hi:
        return 0
    return upper_bound(a, hi) - lower_bound(a, lo)


def nearest(a: Sequence[float], x: float) -> float:
    if not a:
        raise ValueError("empty sequence")
    i = lower_bound(a, x)
    if i == 0:
        return a[0]
    if i == len(a):
        return a[-1]
    below, above = a[i - 1], a[i]
    return below if x - below <= above - x else above


def first_true(pred: Callable[[int], bool], lo: int, hi: int) -> int:
    if lo >= hi:
        return hi
    while lo < hi:
        mid = (lo + hi) // 2
        if pred(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo
