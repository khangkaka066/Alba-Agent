"""Run a callable with retries and exponential backoff."""

from dataclasses import dataclass
from typing import Any

from backoff import delay_for
from policy import Policy


class RetryError(Exception):
    """All attempts failed. ``attempts`` is the number of calls made."""

    def __init__(self, attempts, last_error):
        super().__init__(f"gave up after {attempts} attempts: {last_error!r}")
        self.attempts = attempts
        self.last_error = last_error


@dataclass
class Result:
    value: Any
    attempts: int
    total_delay: float


def run_with_retry(fn, policy, sleep):
    """Call ``fn()`` until it returns, following ``policy``.

    * At most ``policy.max_attempts`` calls are made in total.
    * An exception that is not an instance of ``policy.retry_on`` propagates immediately.
    * After a failed attempt that will be followed by another attempt, ``sleep(delay)`` is
      called with ``delay_for(<number of the retry that follows>, ...)``. Nothing is slept
      after the final failed attempt.
    * ``Result.total_delay`` is the sum of the delays passed to ``sleep`` and
      ``Result.attempts`` the number of calls made.
    * When every attempt fails, ``RetryError(attempts, last_error)`` is raised.
    """
    total_delay = 0.0
    last_error = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return Result(fn(), attempt, total_delay)
        except policy.retry_on as exc:
            last_error = exc
            if attempt < policy.max_attempts:
                delay = delay_for(attempt, policy.base, policy.factor, policy.cap)
                sleep(delay)
                total_delay += delay
    raise RetryError(policy.max_attempts, last_error) from last_error
