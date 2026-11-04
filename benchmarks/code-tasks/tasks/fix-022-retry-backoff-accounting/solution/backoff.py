"""Exponential backoff schedule."""


def delay_for(retry_number, base, factor, cap):
    """Seconds to wait before retry number ``retry_number`` (1 is the first retry).

    The first retry waits ``base`` seconds and every further retry multiplies the wait by
    ``factor``; the result never exceeds ``cap``.
    """
    return min(cap, base * factor ** (retry_number - 1))
