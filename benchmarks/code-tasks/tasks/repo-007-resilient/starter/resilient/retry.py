"""Calling something that may fail."""

from .backoff import delays


def call_with_retry(fn, attempts, base, factor, cap, sleep, retry_on=(Exception,)):
    """Call ``fn()`` up to ``attempts`` times (``attempts`` must be an int >= 1, else ValueError) and return its value as
    soon as one call succeeds.

    When a call raises an exception that is an instance of ``retry_on`` (a tuple of classes) and more attempts remain,
    call ``sleep(seconds)`` with the next value of ``delays(base, factor, cap, attempts - 1)`` and try again, so ``sleep``
    is called once per failed attempt except the last. An exception that is not an instance of ``retry_on`` propagates
    at once, without sleeping. When the last attempt fails, its exception propagates.
    """
    if not isinstance(attempts, int) or attempts < 1:
        raise ValueError("attempts must be an int >= 1")
    waits = delays(base, factor, cap, attempts)
    for index in range(attempts):
        try:
            return fn()
        except Exception as error:
            sleep(waits[index])
            if index == attempts - 1:
                raise error
