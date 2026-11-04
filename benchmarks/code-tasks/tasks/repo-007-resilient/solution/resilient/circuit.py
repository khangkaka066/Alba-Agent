"""A circuit breaker."""


class BreakerOpen(Exception):
    pass


class Breaker:
    """Stops calling something that keeps failing.

    ``threshold`` consecutive failures open the breaker at time ``clock()``. While it is open ``call`` raises
    BreakerOpen without calling ``fn``, until ``clock() - opened_at >= reset_after``. After that one trial call is
    allowed: if it succeeds the breaker closes and the failure count is 0; if it fails the breaker opens again at the
    current ``clock()`` and the exception propagates. In the closed state a success resets the consecutive-failure
    count to 0 and a failure (any Exception) adds one and propagates.
    """

    def __init__(self, threshold, reset_after, clock):
        self.threshold = threshold
        self.reset_after = reset_after
        self.clock = clock
        self.failures = 0
        self.opened_at = None

    def call(self, fn):
        trial = False
        if self.opened_at is not None:
            if self.clock() - self.opened_at < self.reset_after:
                raise BreakerOpen()
            trial = True
        try:
            result = fn()
        except Exception:
            if trial:
                self.opened_at = self.clock()
            else:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = self.clock()
            raise
        self.failures = 0
        self.opened_at = None
        return result
