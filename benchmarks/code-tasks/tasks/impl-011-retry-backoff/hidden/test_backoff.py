import unittest

from backoff import backoff_delays, total_wait


class BackoffTests(unittest.TestCase):
    def test_exponential_default(self):
        self.assertEqual(backoff_delays(4, 1), [1.0, 2.0, 4.0, 8.0])
        self.assertEqual(backoff_delays(3, 0.5), [0.5, 1.0, 2.0])

    def test_custom_factor(self):
        self.assertEqual(backoff_delays(3, 2, factor=3), [2.0, 6.0, 18.0])
        self.assertEqual(backoff_delays(3, 1.5, factor=1), [1.5, 1.5, 1.5])

    def test_zero_retries_and_zero_base(self):
        self.assertEqual(backoff_delays(0, 1), [])
        self.assertEqual(backoff_delays(3, 0), [0.0, 0.0, 0.0])

    def test_max_delay_caps(self):
        self.assertEqual(backoff_delays(6, 1, max_delay=10), [1.0, 2.0, 4.0, 8.0, 10.0, 10.0])
        self.assertEqual(backoff_delays(2, 5, max_delay=0), [0.0, 0.0])

    def test_budget_stops_before_exceeding(self):
        self.assertEqual(backoff_delays(10, 1, budget=10), [1.0, 2.0, 4.0])  # +8 would make 15
        self.assertEqual(backoff_delays(10, 1, budget=15), [1.0, 2.0, 4.0, 8.0])  # exactly 15 allowed
        self.assertEqual(backoff_delays(10, 1, budget=0.5), [])

    def test_budget_does_not_skip_to_later_smaller_delays(self):
        # capped delays are constant, but the first one that doesn't fit ends the schedule
        self.assertEqual(backoff_delays(5, 4, max_delay=4, budget=10), [4.0, 4.0])

    def test_budget_and_retry_limit_interact(self):
        self.assertEqual(backoff_delays(2, 1, budget=100), [1.0, 2.0])
        self.assertEqual(backoff_delays(3, 0, budget=0), [0.0, 0.0, 0.0])

    def test_returns_floats(self):
        for d in backoff_delays(3, 1):
            self.assertIsInstance(d, float)
        for d in backoff_delays(2, 3, max_delay=2):
            self.assertIsInstance(d, float)

    def test_validation(self):
        bad_calls = [
            dict(max_retries=-1, base=1),
            dict(max_retries=1, base=-0.1),
            dict(max_retries=1, base=1, factor=0.5),
            dict(max_retries=1, base=1, max_delay=-1),
            dict(max_retries=1, base=1, budget=-1),
        ]
        for kwargs in bad_calls:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    backoff_delays(**kwargs)

    def test_total_wait(self):
        self.assertEqual(total_wait([]), 0.0)
        self.assertIsInstance(total_wait([]), float)
        self.assertEqual(total_wait([1.0, 2.0, 4.0]), 7.0)
        self.assertEqual(total_wait(backoff_delays(5, 1)), 31.0)


if __name__ == "__main__":
    unittest.main()
