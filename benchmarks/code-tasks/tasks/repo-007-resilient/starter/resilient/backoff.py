"""Waiting times between attempts."""


def delays(base, factor, cap, n):
    """The first ``n`` waiting times, in seconds: the i-th (starting at 0) is ``base * factor ** i`` but never more than
    ``cap``. ``n <= 0`` gives ``[]``. ``base`` must be > 0, ``factor`` >= 1 and ``cap`` >= ``base``, otherwise ValueError
    (even when ``n`` is 0)."""
    if base <= 0 or factor < 1 or cap < base:
        raise ValueError("invalid backoff parameters")
    return [base * factor ** i for i in range(max(n, 0))]
