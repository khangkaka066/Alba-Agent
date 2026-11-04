import unittest

from ratelimit import TokenBucket


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return self.now


class TokenBucketTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def test_starts_full_and_drains(self):
        b = TokenBucket(3, 1.0, self.clock)
        self.assertEqual([b.allow() for _ in range(5)], [True, True, True, False, False])

    def test_refills_over_time(self):
        b = TokenBucket(4, 2.0, self.clock)
        for _ in range(4):
            self.assertTrue(b.allow())
        self.assertFalse(b.allow())
        self.clock.now += 0.5  # +1 token
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())
        self.clock.now += 1.0  # +2 tokens
        self.assertTrue(b.allow(2))
        self.assertFalse(b.allow())

    def test_refill_is_capped_at_capacity(self):
        b = TokenBucket(4, 2.0, self.clock)
        self.assertTrue(b.allow(4))
        self.clock.now += 1000
        self.assertEqual(b.available(), 4.0)

    def test_failed_allow_consumes_nothing(self):
        b = TokenBucket(5, 1.0, self.clock)
        self.assertTrue(b.allow(4))
        self.assertFalse(b.allow(2))
        self.assertEqual(b.available(), 1.0)
        self.assertTrue(b.allow(1))

    def test_fractional_tokens_accumulate(self):
        b = TokenBucket(2, 0.5, self.clock)
        self.assertTrue(b.allow(2))
        self.clock.now += 1.0
        self.assertEqual(b.available(), 0.5)
        self.assertFalse(b.allow())
        self.clock.now += 1.0
        self.assertEqual(b.available(), 1.0)
        self.assertTrue(b.allow())

    def test_retry_after(self):
        b = TokenBucket(4, 2.0, self.clock)
        self.assertEqual(b.retry_after(), 0.0)
        self.assertTrue(b.allow(4))
        self.assertEqual(b.retry_after(), 0.5)
        self.assertEqual(b.retry_after(4), 2.0)
        self.clock.now += 0.25  # 0.5 tokens
        self.assertEqual(b.retry_after(2), 0.75)
        self.assertEqual(b.available(), 0.5)  # retry_after did not consume

    def test_clock_going_backwards_adds_nothing(self):
        b = TokenBucket(2, 1.0, self.clock)
        self.assertTrue(b.allow(2))
        self.clock.now -= 50
        self.assertFalse(b.allow())
        self.clock.now += 1  # last was rewound to now-50, so this adds exactly 1 token
        self.assertTrue(b.allow())
        self.assertFalse(b.allow())

    def test_reset(self):
        b = TokenBucket(3, 1.0, self.clock)
        self.assertTrue(b.allow(3))
        b.reset()
        self.assertEqual(b.available(), 3.0)

    def test_validation(self):
        for args in [(0, 1.0), (-1, 1.0), (1, 0), (1, -2.0)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    TokenBucket(args[0], args[1], self.clock)
        b = TokenBucket(3, 1.0, self.clock)
        for cost in (0, -1, 4):
            with self.subTest(cost=cost):
                with self.assertRaises(ValueError):
                    b.allow(cost)
                with self.assertRaises(ValueError):
                    b.retry_after(cost)
        self.assertEqual(b.available(), 3.0)

    def test_one_clock_read_per_operation(self):
        b = TokenBucket(3, 1.0, self.clock)
        before = self.clock.calls
        b.allow()
        self.assertEqual(self.clock.calls - before, 1)


if __name__ == "__main__":
    unittest.main()
