import unittest

from policy import Policy
from retry import RetryError, run_with_retry


class Flaky:
    def __init__(self, failures, error=ValueError):
        self.failures = failures
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("boom")
        return "ok"


class RetryTests(unittest.TestCase):
    def test_success_after_two_failures_sleeps_with_backoff(self):
        sleeps = []
        result = run_with_retry(Flaky(2), Policy(max_attempts=4, base=1.0, factor=2.0), sleeps.append)
        self.assertEqual((result.value, result.attempts), ("ok", 3))
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(result.total_delay, 3.0)

    def test_first_try_success_does_not_sleep(self):
        sleeps = []
        result = run_with_retry(Flaky(0), Policy(), sleeps.append)
        self.assertEqual((result.attempts, result.total_delay, sleeps), (1, 0.0, []))

    def test_unlisted_exception_propagates(self):
        flaky = Flaky(5, error=KeyError)
        with self.assertRaises(KeyError):
            run_with_retry(flaky, Policy(retry_on=(ValueError,)), lambda s: None)
        self.assertEqual(flaky.calls, 1)


if __name__ == "__main__":
    unittest.main()
