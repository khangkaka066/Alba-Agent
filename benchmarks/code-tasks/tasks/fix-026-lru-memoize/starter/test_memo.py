import unittest

from lru import LRUCache
from memo import memoize


class MemoTests(unittest.TestCase):
    def test_overwriting_counts_as_use(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 10)
        cache.put("c", 3)
        self.assertEqual(cache.keys(), ["a", "c"])
        self.assertIsNone(cache.peek("b"))

    def test_memoize_caches_results(self):
        calls = []

        @memoize(maxsize=4)
        def square(x):
            calls.append(x)
            return x * x

        self.assertEqual([square(2), square(2), square(3)], [4, 4, 9])
        self.assertEqual(calls, [2, 3])
        self.assertEqual(square.cache_info(), {"hits": 1, "misses": 2, "size": 2})

    def test_none_result_is_cached(self):
        calls = []

        @memoize()
        def nothing(x):
            calls.append(x)
            return None

        nothing(1)
        nothing(1)
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
