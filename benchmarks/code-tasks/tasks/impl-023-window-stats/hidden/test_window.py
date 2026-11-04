import unittest

from window import WindowStats


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now
        self.reads = 0

    def __call__(self):
        self.reads += 1
        return self.now


class WindowStatsTests(unittest.TestCase):
    def make(self, seconds=10):
        clock = FakeClock()
        return WindowStats(seconds, clock), clock

    def test_invalid_window(self):
        for bad in (0, -1, -0.5):
            with self.assertRaises(ValueError):
                WindowStats(bad, FakeClock())

    def test_empty(self):
        stats, _ = self.make()
        self.assertEqual(stats.count(), 0)
        self.assertEqual(stats.total(), 0)
        self.assertIsNone(stats.mean())
        self.assertIsNone(stats.minimum())
        self.assertIsNone(stats.maximum())
        self.assertEqual(stats.rate_per_second(), 0)
        self.assertEqual(
            stats.snapshot(), {"count": 0, "total": 0, "mean": None, "min": None, "max": None}
        )

    def test_basic_stats(self):
        stats, clock = self.make()
        for t, v in [(0, 4), (1, 10), (2, 1), (3, 5)]:
            clock.now = t
            stats.add(v)
        clock.now = 4
        self.assertEqual(stats.count(), 4)
        self.assertEqual(stats.total(), 20)
        self.assertEqual(stats.mean(), 5)
        self.assertEqual(stats.minimum(), 1)
        self.assertEqual(stats.maximum(), 10)
        self.assertEqual(stats.rate_per_second(), 0.4)

    def test_expiry_boundary_is_strict(self):
        stats, clock = self.make(10)
        clock.now = 0
        stats.add(100)
        clock.now = 5
        stats.add(1)
        clock.now = 9.999
        self.assertEqual(stats.count(), 2)
        clock.now = 10  # the first sample is exactly 10s old: expired
        self.assertEqual(stats.count(), 1)
        self.assertEqual(stats.maximum(), 1)
        clock.now = 15
        self.assertEqual(stats.count(), 0)
        self.assertIsNone(stats.mean())

    def test_extremes_recomputed_after_expiry(self):
        stats, clock = self.make(5)
        for t, v in [(0, 50), (1, 2), (2, 30), (3, 7)]:
            clock.now = t
            stats.add(v)
        self.assertEqual(stats.maximum(), 50)
        self.assertEqual(stats.minimum(), 2)
        clock.now = 5.5  # drops the samples from t=0 only
        self.assertEqual(stats.maximum(), 30)
        self.assertEqual(stats.minimum(), 2)
        clock.now = 6.5  # drops t=1 as well
        self.assertEqual(stats.minimum(), 7)
        self.assertEqual(stats.maximum(), 30)
        self.assertEqual(stats.total(), 37)

    def test_equal_timestamps(self):
        stats, clock = self.make(1)
        for v in (3, 3, 4):
            stats.add(v)
        self.assertEqual(stats.count(), 3)
        self.assertEqual(stats.mean(), 10 / 3)
        clock.now = 1
        self.assertEqual(stats.count(), 0)

    def test_negative_and_float_values(self):
        stats, clock = self.make(10)
        for v in (-2.5, 1.5, -0.5):
            stats.add(v)
        self.assertEqual(stats.minimum(), -2.5)
        self.assertEqual(stats.maximum(), 1.5)
        self.assertEqual(stats.total(), -1.5)
        self.assertAlmostEqual(stats.mean(), -0.5)

    def test_snapshot_matches_methods(self):
        stats, clock = self.make(10)
        for t, v in [(0, 2), (3, 8), (4, 5)]:
            clock.now = t
            stats.add(v)
        clock.now = 11
        self.assertEqual(
            stats.snapshot(), {"count": 2, "total": 13, "mean": 6.5, "min": 5, "max": 8}
        )

    def test_uses_injected_clock_for_queries(self):
        stats, clock = self.make(10)
        stats.add(1)
        before = clock.reads
        stats.count()
        self.assertGreater(clock.reads, before)

    def test_many_samples_efficient(self):
        stats, clock = self.make(1000)
        for i in range(30000):
            clock.now = float(i)
            stats.add(i)
        clock.now = 30000.0
        # samples with 30000 - timestamp < 1000 survive: 29001..29999
        self.assertEqual(stats.count(), 999)
        self.assertEqual(stats.minimum(), 29001)
        self.assertEqual(stats.maximum(), 29999)


if __name__ == "__main__":
    unittest.main()
