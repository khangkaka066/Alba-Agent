"""Small statistics helpers used by the reporting module."""


def mean(values):
    """Arithmetic mean as a float. Raises ValueError for an empty sequence."""
    if not values:
        raise ValueError("mean of empty sequence")
    return sum(values) / len(values)


def median(values):
    """Median of a non-empty sequence (input is not modified).

    For an even number of values it is the true average of the two middle
    values, so median([1, 2, 3, 4]) is 2.5. Raises ValueError if empty.
    """
    if not values:
        raise ValueError("median of empty sequence")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def summarize(values):
    """Return {"mean", "median", "min", "max"} for a non-empty sequence."""
    return {
        "mean": mean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }
