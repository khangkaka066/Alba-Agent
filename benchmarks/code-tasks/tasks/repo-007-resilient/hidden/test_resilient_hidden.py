import unittest

from resilient.backoff import delays
from resilient.circuit import Breaker, BreakerOpen
from resilient.retry import call_with_retry


class Flaky:
    def __init__(self, failures, error=ValueError):
        self.failures, self.error, self.calls = failures, error, 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error(f"failure {self.calls}")
        return f"ok after {self.calls}"


class BackoffTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(delays(1, 2, 5, 5), [1, 2, 4, 5, 5])
        self.assertEqual(delays(0.5, 1, 10, 3), [0.5, 0.5, 0.5])
        self.assertEqual(delays(2, 3, 100, 4), [2, 6, 18, 54])
        self.assertEqual(delays(1, 2, 8, 0), [])
        self.assertEqual(delays(1, 2, 8, -3), [])

    def test_validation(self):
        for args in [(0, 2, 5, 3), (-1, 2, 5, 3), (1, 0.5, 5, 3), (2, 2, 1, 3), (0, 2, 5, 0)]:
            with self.assertRaises(ValueError, msg=args):
                delays(*args)


class RetryTests(unittest.TestCase):
    def test_returns_first_success(self):
        waited = []
        flaky = Flaky(2)
        self.assertEqual(call_with_retry(flaky, 5, 1, 2, 10, waited.append), "ok after 3")
        self.assertEqual(waited, [1, 2])

    def test_no_failure_means_no_sleep(self):
        waited = []
        self.assertEqual(call_with_retry(Flaky(0), 3, 1, 2, 10, waited.append), "ok after 1")
        self.assertEqual(waited, [])

    def test_last_failure_propagates_without_a_final_sleep(self):
        waited = []
        flaky = Flaky(10)
        with self.assertRaises(ValueError) as caught:
            call_with_retry(flaky, 3, 1, 2, 10, waited.append)
        self.assertEqual(str(caught.exception), "failure 3")
        self.assertEqual((flaky.calls, waited), (3, [1, 2]))

    def test_single_attempt(self):
        waited = []
        with self.assertRaises(ValueError):
            call_with_retry(Flaky(5), 1, 1, 2, 10, waited.append)
        self.assertEqual(waited, [])

    def test_delays_respect_the_cap(self):
        waited = []
        with self.assertRaises(ValueError):
            call_with_retry(Flaky(10), 6, 1, 3, 5, waited.append)
        self.assertEqual(waited, [1, 3, 5, 5, 5])

    def test_only_listed_exceptions_are_retried(self):
        waited = []
        flaky = Flaky(5, KeyError)
        with self.assertRaises(KeyError):
            call_with_retry(flaky, 4, 1, 2, 10, waited.append, retry_on=(ValueError,))
        self.assertEqual((flaky.calls, waited), (1, []))

    def test_retry_on_accepts_several_classes(self):
        flaky = Flaky(1, KeyError)
        self.assertEqual(call_with_retry(flaky, 3, 1, 2, 10, lambda s: None, retry_on=(ValueError, KeyError)), "ok after 2")

    def test_bad_attempts(self):
        for bad in (0, -1, 1.5, "2"):
            with self.assertRaises(ValueError):
                call_with_retry(Flaky(0), bad, 1, 2, 10, lambda s: None)


class BreakerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.breaker = Breaker(3, 10, lambda: self.now)

    def fail(self):
        raise RuntimeError("down")

    def trip(self):
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                self.breaker.call(self.fail)

    def test_opens_after_consecutive_failures(self):
        self.trip()
        called = []
        with self.assertRaises(BreakerOpen):
            self.breaker.call(lambda: called.append(1))
        self.assertEqual(called, [])

    def test_failures_must_be_consecutive(self):
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.breaker.call(self.fail)
        self.assertEqual(self.breaker.call(lambda: "fine"), "fine")
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.breaker.call(self.fail)
        self.assertEqual(self.breaker.call(lambda: "still closed"), "still closed")

    def test_stays_open_until_reset_after(self):
        self.trip()
        self.now = 9.9
        with self.assertRaises(BreakerOpen):
            self.breaker.call(lambda: 1)
        self.now = 10
        self.assertEqual(self.breaker.call(lambda: "trial"), "trial")
        self.assertEqual(self.breaker.call(lambda: "closed"), "closed")

    def test_failed_trial_reopens_from_now(self):
        self.trip()
        self.now = 10
        with self.assertRaises(RuntimeError):
            self.breaker.call(self.fail)
        self.now = 15
        with self.assertRaises(BreakerOpen):
            self.breaker.call(lambda: 1)
        self.now = 20
        self.assertEqual(self.breaker.call(lambda: "ok"), "ok")

    def test_after_closing_a_full_threshold_is_needed_again(self):
        self.trip()
        self.now = 10
        self.breaker.call(lambda: 1)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.breaker.call(self.fail)
        self.assertEqual(self.breaker.call(lambda: "closed"), "closed")

    def test_exceptions_from_the_trial_propagate_unchanged(self):
        self.trip()
        self.now = 11
        with self.assertRaises(RuntimeError) as caught:
            self.breaker.call(self.fail)
        self.assertEqual(str(caught.exception), "down")


if __name__ == "__main__":
    unittest.main()
