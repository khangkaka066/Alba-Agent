"""Retry policy value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    """How to retry.

    ``max_attempts`` is the total number of calls including the first one. ``base``,
    ``factor`` and ``cap`` shape the exponential backoff (see ``backoff.delay_for``).
    Only exceptions that are instances of ``retry_on`` are retried.
    """

    max_attempts: int = 3
    base: float = 1.0
    factor: float = 2.0
    cap: float = 30.0
    retry_on: tuple = (Exception,)

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base < 0 or self.cap < 0 or self.factor < 1:
            raise ValueError("base and cap must be >= 0 and factor >= 1")
