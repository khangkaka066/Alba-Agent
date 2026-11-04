import unittest

from lru import LRUStore


class LRUTests(unittest.TestCase):
    def test_evicts_oldest(self):
        s = LRUStore(2)
        s.put("a", 1)
        s.put("b", 2)
        s.put("c", 3)
        self.assertEqual(s.keys(), ["b", "c"])

    def test_get_refreshes(self):
        s = LRUStore(2)
        s.put("a", 1)
        s.put("b", 2)
        self.assertEqual(s.get("a"), 1)
        s.put("c", 3)
        self.assertEqual(s.keys(), ["a", "c"])

    def test_on_evict_called(self):
        seen = []
        s = LRUStore(1, on_evict=lambda k, v: seen.append((k, v)))
        s.put("a", 1)
        s.put("b", 2)
        self.assertEqual(seen, [("a", 1)])


if __name__ == "__main__":
    unittest.main()
