import random
import unittest

from limiter import WindowLimiter


class Model:
    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.ev = {}
        self.last = {}

    def used(self, k, now):
        return sum(c for t, c in self.ev.get(k, []) if t > now - self.window)

    def allow(self, k, now, cost):
        self.last[k] = now
        if cost > self.limit or self.used(k, now) + cost > self.limit:
            return False
        self.ev.setdefault(k, []).append((now, cost))
        return True

    def retry(self, k, now, cost):
        if cost > self.limit:
            return None
        if self.used(k, now) + cost <= self.limit:
            return 0
        cands = sorted(t + self.window for t, _ in self.ev[k] if t > now - self.window)
        for c in cands:
            if self.used(k, c) + cost <= self.limit:
                return c - now
        raise AssertionError


class LimiterTests(unittest.TestCase):
    def test_basic_and_boundary(self):
        l = WindowLimiter(2, 10)
        self.assertTrue(l.allow("a", 0))
        self.assertTrue(l.allow("a", 5))
        self.assertFalse(l.allow("a", 9.99))
        self.assertTrue(l.allow("a", 10))      # t=0 expired exactly at 10
        self.assertFalse(l.allow("a", 10))     # 5 and 10 counted
        self.assertTrue(l.allow("a", 15))

    def test_rejected_not_recorded(self):
        l = WindowLimiter(1, 10)
        self.assertTrue(l.allow("a", 0))
        for t in (1, 2, 3, 9):
            self.assertFalse(l.allow("a", t))
        self.assertTrue(l.allow("a", 10))   # rejections must not have pushed expiry out

    def test_idle_gap_then_burst(self):
        l = WindowLimiter(3, 10)
        for t in (0, 1, 2):
            self.assertTrue(l.allow("a", t))
        self.assertFalse(l.allow("a", 3))
        # long idle gap: full budget again, and exactly `limit` more are allowed
        self.assertEqual([l.allow("a", 1000) for _ in range(5)], [True, True, True, False, False])
        self.assertEqual(l.remaining("a", 1000), 0)
        self.assertEqual(l.remaining("a", 1010), 3)

    def test_cost(self):
        l = WindowLimiter(5, 10)
        self.assertTrue(l.allow("a", 0, 3))
        self.assertFalse(l.allow("a", 1, 3))
        self.assertTrue(l.allow("a", 2, 2))
        self.assertFalse(l.allow("a", 3, 6))      # cost > limit
        self.assertEqual(l.remaining("a", 3), 0)
        self.assertEqual(l.remaining("a", 10), 3)
        self.assertTrue(l.allow("a", 10, 3))

    def test_retry_after(self):
        l = WindowLimiter(2, 10)
        l.allow("a", 0)
        l.allow("a", 4)
        self.assertEqual(l.retry_after("a", 5), 5)
        self.assertEqual(l.retry_after("a", 5, 2), 9)
        self.assertEqual(l.retry_after("a", 5, 3), None)
        self.assertEqual(l.retry_after("zz", 5), 0)
        self.assertEqual(l.retry_after("a", 10), 0)
        # retry_after / remaining must not mutate
        self.assertFalse(l.allow("a", 5))
        self.assertEqual(l.remaining("a", 5), 0)
        self.assertTrue(l.allow("a", 10))

    def test_keys_independent(self):
        l = WindowLimiter(1, 10)
        self.assertTrue(l.allow("a", 0))
        self.assertTrue(l.allow("b", 0))
        self.assertFalse(l.allow("a", 1))

    def test_time_backwards(self):
        l = WindowLimiter(2, 10)
        l.allow("a", 5)
        with self.assertRaises(ValueError):
            l.allow("a", 4)
        with self.assertRaises(ValueError):
            l.remaining("a", 4)
        with self.assertRaises(ValueError):
            l.retry_after("a", 4)
        self.assertEqual(l.remaining("a", 5), 1)
        self.assertTrue(l.allow("a", 5))
        self.assertTrue(l.allow("b", 1))     # other key unaffected
        l.remaining("fresh", -100)           # never allowed -> no bound

    def test_validation(self):
        for args in ((0, 1), (1, 0), (1, -1)):
            with self.assertRaises(ValueError):
                WindowLimiter(*args)
        l = WindowLimiter(2, 1)
        with self.assertRaises(ValueError):
            l.allow("a", 0, 0)
        with self.assertRaises(ValueError):
            l.allow("a", 0, -2)

    def test_idle_state_not_retained(self):
        l = WindowLimiter(5, 1)
        for i in range(2000):
            l.allow("a", i * 10.0)
        l.allow("a", 1e6)
        stored = 0
        for v in vars(l).values():
            if isinstance(v, dict):
                for item in v.values():
                    try:
                        stored += len(item)
                    except TypeError:
                        pass
        self.assertLess(stored, 20)

    def test_random_sequences_match_model(self):
        rng = random.Random(1234)
        for limit, window in ((1, 5), (3, 10), (5, 7)):
            l, m = WindowLimiter(limit, window), Model(limit, window)
            clock = {k: 0 for k in "xyz"}
            for _ in range(2500):
                k = rng.choice("xyz")
                gap = rng.choice([0, 0, 1, 1, 2, 3, window, window - 1, window + 1, 5 * window])
                clock[k] += gap
                now = clock[k]
                op = rng.choice(["allow", "allow", "allow", "remaining", "retry"])
                cost = rng.choice([1, 1, 1, 2, limit, limit + 1])
                if op == "allow":
                    self.assertEqual(l.allow(k, now, cost), m.allow(k, now, cost), (k, now, cost))
                elif op == "remaining":
                    self.assertEqual(l.remaining(k, now), limit - m.used(k, now))
                else:
                    self.assertEqual(l.retry_after(k, now, cost), m.retry(k, now, cost))


if __name__ == "__main__":
    unittest.main()
