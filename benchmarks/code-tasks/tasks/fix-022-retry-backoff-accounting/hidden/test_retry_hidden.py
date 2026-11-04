import unittest

from backoff import delay_for
from policy import Policy
from retry import RetryError, run_with_retry


def always_fail():
    raise ValueError("nope")


class RetryHiddenTests(unittest.TestCase):
    def test_delay_schedule(self):
        self.assertEqual([delay_for(n, 0.5, 2.0, 100.0) for n in (1, 2, 3, 4)], [0.5, 1.0, 2.0, 4.0])
        self.assertEqual(delay_for(1, 3.0, 5.0, 100.0), 3.0)
        self.assertEqual(delay_for(3, 1.0, 1.0, 100.0), 1.0)

    def test_delay_is_capped(self):
        self.assertEqual(delay_for(6, 1.0, 2.0, 10.0), 10.0)
        self.assertEqual(delay_for(1, 50.0, 2.0, 10.0), 10.0)

    def test_exhaustion_sleeps_only_between_attempts(self):
        sleeps = []
        calls = []

        def fn():
            calls.append(1)
            raise ValueError("x")

        with self.assertRaises(RetryError) as ctx:
            run_with_retry(fn, Policy(max_attempts=3, base=1.0, factor=3.0), sleeps.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1.0, 3.0])
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertIsInstance(ctx.exception.last_error, ValueError)

    def test_single_attempt_policy_never_sleeps(self):
        sleeps = []
        with self.assertRaises(RetryError) as ctx:
            run_with_retry(always_fail, Policy(max_attempts=1), sleeps.append)
        self.assertEqual((sleeps, ctx.exception.attempts), ([], 1))

    def test_total_delay_matches_sleeps_with_cap(self):
        sleeps = []
        state = {"n": 0}

        def fn():
            state["n"] += 1
            if state["n"] < 6:
                raise ValueError
            return state["n"]

        result = run_with_retry(fn, Policy(max_attempts=6, base=1.0, factor=2.0, cap=5.0), sleeps.append)
        self.assertEqual(sleeps, [1.0, 2.0, 4.0, 5.0, 5.0])
        self.assertEqual(result.total_delay, sum(sleeps))
        self.assertEqual((result.value, result.attempts), (6, 6))

    def test_success_on_last_allowed_attempt(self):
        state = {"n": 0}

        def fn():
            state["n"] += 1
            if state["n"] < 3:
                raise ValueError
            return "done"

        result = run_with_retry(fn, Policy(max_attempts=3, base=0.5), lambda s: None)
        self.assertEqual((result.value, result.attempts, result.total_delay), ("done", 3, 1.5))

    def test_only_listed_exceptions_are_retried(self):
        calls = []

        def fn():
            calls.append(1)
            if len(calls) == 1:
                raise ValueError
            raise KeyError("k")

        with self.assertRaises(KeyError):
            run_with_retry(fn, Policy(max_attempts=5, retry_on=(ValueError,)), lambda s: None)
        self.assertEqual(len(calls), 2)

    def test_policy_validation(self):
        for kwargs in ({"max_attempts": 0}, {"base": -1}, {"factor": 0.5}, {"cap": -1}):
            with self.assertRaises(ValueError):
                Policy(**kwargs)


if __name__ == "__main__":
    unittest.main()
