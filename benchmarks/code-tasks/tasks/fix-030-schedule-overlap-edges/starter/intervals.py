"""Half-open time intervals measured in whole minutes."""

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Interval:
    """The minutes ``start, start+1, ..., end-1``: ``start`` is included, ``end`` is not.

    ``Interval(9 * 60, 10 * 60)`` and ``Interval(10 * 60, 11 * 60)`` therefore do not
    share any minute. ``start`` must be smaller than ``end`` (ValueError otherwise).
    """

    start: int
    end: int

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError("start must be before end")

    @property
    def length(self):
        return self.end - self.start


def overlaps(a, b):
    """True when the two intervals share at least one minute."""
    return a.start <= b.end and b.start <= a.end


def merge(intervals):
    """Union of intervals as a sorted list of disjoint intervals.

    Intervals that overlap or merely touch (one ends exactly where the next starts) are
    joined into one.
    """
    merged = []
    for iv in sorted(intervals):
        if merged and iv.start <= merged[-1].end:
            last = merged[-1]
            merged[-1] = Interval(last.start, max(last.end, iv.end))
        else:
            merged.append(iv)
    return merged
