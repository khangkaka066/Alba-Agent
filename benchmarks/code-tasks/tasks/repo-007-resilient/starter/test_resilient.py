import unittest

from resilient.backoff import delays
from resilient.circuit import Breaker, BreakerOpen
from resilient.retry import call_with_retry


class ResilientTests(unittest.TestCase):
    def test_delays_are_capped(self):
        self.assertEqual(delays(1, 2, 5, 5), [1, 2, 4, 5, 5])

    def test_only_listed_exceptions_are_retried(self):
        calls = []

        def boom():
            calls.append(1)
            raise KeyError("x")

        with self.assertRaises(KeyError):
            call_with_retry(boom, 3, 1, 2, 10, lambda s: None, retry_on=(ValueError,))
        self.assertEqual(len(calls), 1)

    def test_no_sleep_after_the_last_attempt(self):
        waited = []

        def boom():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            call_with_retry(boom, 3, 1, 2, 10, waited.append)
        self.assertEqual(waited, [1, 2])

    def test_success_resets_the_failure_count(self):
        now = [0]
        breaker = Breaker(2, 10, lambda: now[0])

        def fail():
            raise RuntimeError("x")

        with self.assertRaises(RuntimeError):
            breaker.call(fail)
        breaker.call(lambda: 1)
        with self.assertRaises(RuntimeError):
            breaker.call(fail)
        self.assertEqual(breaker.call(lambda: 2), 2)


if __name__ == "__main__":
    unittest.main()
