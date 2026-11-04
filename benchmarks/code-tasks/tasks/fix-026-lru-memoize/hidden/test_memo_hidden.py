import unittest

from lru import LRUCache
from memo import memoize


class LruHiddenTests(unittest.TestCase):
    def test_eviction_order_basic(self):
        c = LRUCache(3)
        for k in "abc":
            c.put(k, k.upper())
        self.assertEqual(c.put("d", "D"), ("a", "A"))
        self.assertEqual(c.keys(), ["b", "c", "d"])

    def test_get_refreshes(self):
        c = LRUCache(3)
        for k in "abc":
            c.put(k, 0)
        c.get("a")
        c.put("d", 0)
        self.assertEqual(c.keys(), ["c", "a", "d"])

    def test_overwrite_refreshes_and_does_not_evict(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertIsNone(c.put("a", 3))
        self.assertEqual(c.keys(), ["b", "a"])
        self.assertEqual(c.put("c", 4), ("b", 2))
        self.assertEqual(c.peek("a"), 3)
        self.assertEqual(len(c), 2)

    def test_peek_contains_len_do_not_refresh(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.peek("a")
        _ = "a" in c
        _ = len(c)
        self.assertEqual(c.keys(), ["a", "b"])
        c.put("c", 3)
        self.assertNotIn("a", c)

    def test_get_default_and_falsy_values(self):
        c = LRUCache(2)
        c.put("z", 0)
        self.assertEqual(c.get("z", "d"), 0)
        self.assertEqual(c.get("missing", "d"), "d")
        self.assertIsNone(c.get("missing"))

    def test_capacity_one_and_validation(self):
        c = LRUCache(1)
        c.put("a", 1)
        self.assertEqual(c.put("b", 2), ("a", 1))
        self.assertEqual(c.keys(), ["b"])
        with self.assertRaises(ValueError):
            LRUCache(0)


class MemoHiddenTests(unittest.TestCase):
    def test_falsy_results_are_cached(self):
        calls = []

        @memoize()
        def f(x):
            calls.append(x)
            return [None, 0, "", False, ()][x]

        results = [f(i) for i in range(5)] + [f(i) for i in range(5)]
        self.assertEqual(results, [None, 0, "", False, ()] * 2)
        self.assertEqual(calls, [0, 1, 2, 3, 4])
        self.assertEqual(f.cache_info(), {"hits": 5, "misses": 5, "size": 5})

    def test_eviction_recomputes_least_recent(self):
        calls = []

        @memoize(maxsize=2)
        def f(x):
            calls.append(x)
            return x

        f(1)
        f(2)
        f(1)
        f(3)  # evicts 2
        f(1)  # still cached
        f(2)  # recomputed
        self.assertEqual(calls, [1, 2, 3, 2])
        self.assertEqual(f.cache_info(), {"hits": 2, "misses": 4, "size": 2})

    def test_kwargs_order_does_not_matter_and_args_do(self):
        calls = []

        @memoize()
        def f(a, b=0, c=0):
            calls.append((a, b, c))
            return a + b + c

        f(1, b=2, c=3)
        f(1, c=3, b=2)
        f(1, 2, 3)
        self.assertEqual(len(calls), 2)

    def test_wrapper_keeps_metadata(self):
        @memoize()
        def documented(x):
            """doc"""
            return x

        self.assertEqual(documented.__name__, "documented")
        self.assertEqual(documented.__doc__, "doc")
        self.assertIsInstance(documented.cache, LRUCache)


if __name__ == "__main__":
    unittest.main()
