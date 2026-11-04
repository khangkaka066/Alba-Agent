import random
import unittest

from lru import LRUStore


class Model:
    def __init__(self, cap):
        self.cap = cap
        self.items = []  # [(k, v)] oldest first
        self.evicted = []

    def _find(self, k):
        for i, (kk, _) in enumerate(self.items):
            if kk == k:
                return i
        return None

    def put(self, k, v):
        i = self._find(k)
        if i is not None:
            self.items.pop(i)
        elif len(self.items) >= self.cap:
            self.evicted.append(self.items.pop(0))
        self.items.append((k, v))

    def get(self, k):
        i = self._find(k)
        if i is None:
            return None
        item = self.items.pop(i)
        self.items.append(item)
        return item[1]


class LRUHiddenTests(unittest.TestCase):
    def test_reinsert_after_delete(self):
        s = LRUStore(2)
        s.put("a", 1)
        s.put("b", 2)
        s.delete("a")
        s.put("a", 3)           # a is now newest
        s.put("c", 4)           # must evict b
        self.assertEqual(s.keys(), ["a", "c"])

    def test_overwrite_refreshes_and_never_evicts(self):
        seen = []
        s = LRUStore(2, on_evict=lambda k, v: seen.append(k))
        s.put("a", 1)
        s.put("b", 2)
        s.put("a", 10)
        self.assertEqual(seen, [])
        self.assertEqual(s.keys(), ["b", "a"])
        s.put("c", 3)
        self.assertEqual(seen, ["b"])
        self.assertEqual(s.peek("a"), 10)

    def test_repeated_gets_do_not_accumulate(self):
        s = LRUStore(2)
        s.put("a", 1)
        s.put("b", 2)
        for _ in range(5):
            s.get("a")
        s.get("b")
        s.put("c", 3)
        self.assertEqual(s.keys(), ["b", "c"])
        self.assertEqual(len(s), 2)

    def test_peek_does_not_refresh(self):
        s = LRUStore(2)
        s.put("a", 1)
        s.put("b", 2)
        s.peek("a")
        s.put("c", 3)
        self.assertEqual(s.keys(), ["b", "c"])

    def test_pop_oldest_after_refreshes(self):
        s = LRUStore(3)
        for k in "abc":
            s.put(k, ord(k))
        s.get("a")
        s.put("b", 0)
        self.assertEqual(s.pop_oldest(), ("c", ord("c")))
        self.assertEqual(s.pop_oldest(), ("a", ord("a")))
        self.assertEqual(s.pop_oldest(), ("b", 0))
        with self.assertRaises(KeyError):
            s.pop_oldest()

    def test_delete_then_pop_and_missing(self):
        s = LRUStore(3)
        s.put("a", 1)
        s.put("b", 2)
        self.assertTrue(s.delete("a"))
        self.assertFalse(s.delete("a"))
        self.assertEqual(s.pop_oldest(), ("b", 2))
        self.assertEqual(len(s), 0)
        self.assertEqual(s.get("a", "dflt"), "dflt")

    def test_on_evict_gets_value_and_not_on_delete(self):
        seen = []
        s = LRUStore(1, on_evict=lambda k, v: seen.append((k, v)))
        s.put("a", 1)
        s.delete("a")
        s.put("b", 2)
        s.pop_oldest()
        s.put("c", 3)
        self.assertEqual(seen, [])
        s.put("d", 4)
        self.assertEqual(seen, [("c", 3)])

    def test_none_values(self):
        s = LRUStore(2)
        s.put("a", None)
        s.put("b", None)
        s.get("a")
        s.put("c", None)
        self.assertEqual(s.keys(), ["a", "c"])

    def test_memory_is_bounded(self):
        s = LRUStore(3)
        for i in range(3000):
            s.put(i % 3, i)
            s.get(i % 3)
        n = 0
        for v in vars(s).values():
            if hasattr(v, "__len__") and not isinstance(v, str):
                n = max(n, len(v))
        self.assertLessEqual(n, 3)

    def test_random_sequences_match_model(self):
        rng = random.Random(1234)
        for cap in (1, 2, 3, 5):
            evicted = []
            s = LRUStore(cap, on_evict=lambda k, v: evicted.append((k, v)))
            m = Model(cap)
            for step in range(3000):
                op = rng.choice(["put", "put", "get", "get", "peek", "delete", "pop"])
                k = rng.randrange(cap + 3)
                if op == "put":
                    s.put(k, step)
                    m.put(k, step)
                elif op == "get":
                    self.assertEqual(s.get(k), m.get(k))
                elif op == "peek":
                    i = m._find(k)
                    self.assertEqual(s.peek(k), None if i is None else m.items[i][1])
                elif op == "delete":
                    i = m._find(k)
                    self.assertEqual(s.delete(k), i is not None)
                    if i is not None:
                        m.items.pop(i)
                else:
                    if m.items:
                        self.assertEqual(s.pop_oldest(), m.items.pop(0))
                    else:
                        with self.assertRaises(KeyError):
                            s.pop_oldest()
                self.assertEqual(s.keys(), [k for k, _ in m.items])
                self.assertEqual(len(s), len(m.items))
            self.assertEqual(evicted, m.evicted)


if __name__ == "__main__":
    unittest.main()
