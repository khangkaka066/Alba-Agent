import unittest

from ttlcache import TTLCache


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TTLCacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def make(self, capacity=3, ttl=10.0):
        return TTLCache(capacity, ttl, self.clock)

    def test_basic_get_set_and_default(self):
        c = self.make()
        c.set("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("zzz"))
        self.assertEqual(c.get("zzz", "dflt"), "dflt")
        self.assertEqual(len(c), 1)
        self.assertIn("a", c)
        self.assertNotIn("b", c)

    def test_expiry_boundary_is_exclusive(self):
        c = self.make(ttl=10.0)
        c.set("a", 1)
        self.clock.advance(9.5)
        self.assertEqual(c.get("a"), 1)
        self.clock.advance(0.5)  # exactly t + ttl
        self.assertIsNone(c.get("a"))
        self.assertNotIn("a", c)
        self.assertEqual(len(c), 0)

    def test_get_does_not_extend_lifetime(self):
        c = self.make(ttl=10.0)
        c.set("a", 1)
        self.clock.advance(6)
        self.assertEqual(c.get("a"), 1)
        self.clock.advance(5)
        self.assertEqual(c.get("a", "gone"), "gone")

    def test_set_existing_restarts_lifetime_and_overrides_ttl(self):
        c = self.make(ttl=10.0)
        c.set("a", 1)
        self.clock.advance(8)
        c.set("a", 2)
        self.clock.advance(8)
        self.assertEqual(c.get("a"), 2)
        c.set("b", 3, ttl=1.0)
        self.clock.advance(1)
        self.assertNotIn("b", c)

    def test_lru_eviction_uses_get_recency(self):
        c = self.make(capacity=3)
        for k in "abc":
            c.set(k, k.upper())
        self.assertEqual(c.get("a"), "A")  # a becomes most recent
        c.set("d", "D")  # evicts b
        self.assertEqual(c.keys(), ["c", "a", "d"])
        self.assertNotIn("b", c)

    def test_peek_and_contains_do_not_change_recency(self):
        c = self.make(capacity=2)
        c.set("a", 1)
        c.set("b", 2)
        self.assertEqual(c.peek("a"), 1)
        self.assertIn("a", c)
        c.set("c", 3)  # a is still least recently used
        self.assertEqual(c.keys(), ["b", "c"])

    def test_set_existing_makes_most_recent_without_growing(self):
        c = self.make(capacity=2)
        c.set("a", 1)
        c.set("b", 2)
        c.set("a", 10)
        self.assertEqual(c.keys(), ["b", "a"])
        c.set("c", 3)
        self.assertEqual(c.keys(), ["a", "c"])

    def test_expired_entries_dropped_before_lru_eviction(self):
        c = self.make(capacity=2, ttl=100.0)
        c.set("long", 1)
        c.set("short", 2, ttl=1.0)
        c.get("short")  # short is now the most recent; long is the LRU
        self.clock.advance(2)
        c.set("new", 3)  # short expired: it must go, not "long"
        self.assertEqual(c.keys(), ["long", "new"])

    def test_delete(self):
        c = self.make()
        c.set("a", 1)
        c.set("b", 2, ttl=1.0)
        self.assertTrue(c.delete("a"))
        self.assertFalse(c.delete("a"))
        self.clock.advance(5)
        self.assertFalse(c.delete("b"))
        self.assertEqual(len(c), 0)

    def test_len_and_keys_ignore_expired(self):
        c = self.make()
        c.set("a", 1, ttl=1.0)
        c.set("b", 2)
        c.set("c", 3, ttl=1.0)
        self.clock.advance(1)
        self.assertEqual(len(c), 1)
        self.assertEqual(c.keys(), ["b"])

    def test_none_value_and_clear(self):
        c = self.make()
        c.set("n", None)
        self.assertEqual(c.get("n", "dflt"), None)
        self.assertEqual(c.peek("n", "dflt"), None)
        c.clear()
        self.assertEqual(len(c), 0)
        self.assertEqual(c.keys(), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            TTLCache(0, 1.0, self.clock)
        with self.assertRaises(ValueError):
            TTLCache(1, 0, self.clock)
        with self.assertRaises(ValueError):
            TTLCache(1, -1.0, self.clock)
        c = self.make()
        with self.assertRaises(ValueError):
            c.set("a", 1, ttl=0)
        self.assertNotIn("a", c)

    def test_capacity_one(self):
        c = self.make(capacity=1)
        c.set("a", 1)
        c.set("b", 2)
        self.assertEqual(c.keys(), ["b"])
        self.assertIsNone(c.get("a"))


if __name__ == "__main__":
    unittest.main()
