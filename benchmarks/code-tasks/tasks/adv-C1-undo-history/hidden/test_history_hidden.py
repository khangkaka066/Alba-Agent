import copy
import random
import unittest

from history import History


class Model:
    def __init__(self, initial, limit):
        self.states = [copy.deepcopy(initial)]
        self.idx = 0
        self.limit = limit

    def commit(self, v):
        if v == self.states[self.idx]:
            return False
        self.states = self.states[: self.idx + 1] + [copy.deepcopy(v)]
        self.idx += 1
        if self.limit is not None and self.idx > self.limit:
            d = self.idx - self.limit
            self.states = self.states[d:]
            self.idx -= d
        return True


class HistoryTests(unittest.TestCase):
    def test_basic_undo_redo(self):
        h = History("a")
        self.assertFalse(h.can_undo)
        self.assertTrue(h.commit("b"))
        self.assertTrue(h.commit("c"))
        self.assertEqual(h.undo(), "b")
        self.assertEqual(h.undo(), "a")
        self.assertEqual(h.redo(), "b")
        self.assertEqual((h.undo_steps, h.redo_steps), (1, 1))

    def test_empty_errors_leave_state(self):
        h = History(1)
        with self.assertRaises(IndexError):
            h.undo()
        with self.assertRaises(IndexError):
            h.redo()
        h.commit(2)
        h.undo()
        with self.assertRaises(IndexError):
            h.undo()
        self.assertEqual(h.current, 1)
        self.assertEqual(h.redo_steps, 1)

    def test_new_commit_after_undo_discards_redo(self):
        h = History(0)
        for v in (1, 2, 3):
            h.commit(v)
        h.undo()
        h.undo()
        self.assertTrue(h.commit(9))
        self.assertFalse(h.can_redo)
        with self.assertRaises(IndexError):
            h.redo()
        self.assertEqual(h.undo(), 1)
        self.assertEqual(h.undo(), 0)
        self.assertEqual(h.redo(), 1)
        self.assertEqual(h.redo(), 9)

    def test_equal_commit_keeps_redo(self):
        h = History([1])
        h.commit([1, 2])
        h.undo()
        self.assertFalse(h.commit([1]))
        self.assertEqual(h.redo_steps, 1)
        self.assertEqual(h.redo(), [1, 2])

    def test_limit_trims_oldest(self):
        h = History(0, limit=2)
        for v in (1, 2, 3, 4):
            h.commit(v)
        self.assertEqual(h.undo_steps, 2)
        self.assertEqual(h.undo(), 3)
        self.assertEqual(h.undo(), 2)
        with self.assertRaises(IndexError):
            h.undo()

    def test_limit_after_undo_and_commit(self):
        h = History(0, limit=3)
        for v in (1, 2, 3):
            h.commit(v)
        h.undo()
        h.undo()          # at 1, redo has 2,3
        h.commit(10)      # states 0,1,10 ; idx 2
        self.assertEqual(h.undo_steps, 2)
        h.commit(11)
        h.commit(12)      # 0 dropped
        self.assertEqual(h.undo_steps, 3)
        self.assertEqual([h.undo(), h.undo(), h.undo()], [11, 10, 1])
        with self.assertRaises(IndexError):
            h.undo()

    def test_bad_limit(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                History(0, limit=bad)

    def test_aliasing_input(self):
        doc = {"lines": ["a"]}
        h = History(doc)
        doc["lines"].append("zzz")
        self.assertEqual(h.current, {"lines": ["a"]})
        nxt = {"lines": ["a", "b"]}
        h.commit(nxt)
        nxt["lines"].append("late")
        self.assertEqual(h.current, {"lines": ["a", "b"]})
        self.assertEqual(h.undo(), {"lines": ["a"]})
        self.assertEqual(h.redo(), {"lines": ["a", "b"]})

    def test_aliasing_output(self):
        h = History([1])
        h.commit([1, 2])
        h.current.append(99)
        self.assertEqual(h.current, [1, 2])
        got = h.undo()
        got.append(7)
        self.assertEqual(h.current, [1])
        self.assertEqual(h.redo(), [1, 2])
        h.redo  # no-op attribute access
        r = h.undo()
        r.clear()
        self.assertEqual(h.undo_steps, 0)
        self.assertEqual(h.current, [1])

    def test_commit_after_mutating_current_copy_is_detected(self):
        h = History([1])
        c = h.current
        c.append(2)
        self.assertTrue(h.commit(c))
        self.assertEqual(h.undo(), [1])

    def test_random_sequences_match_model(self):
        rng = random.Random(1234)
        for limit in (None, 1, 2, 5):
            h = History([0], limit=limit)
            m = Model([0], limit)
            for _ in range(1500):
                op = rng.choice(["commit", "commit", "undo", "undo", "redo", "same", "mutate"])
                if op == "commit":
                    v = [rng.randrange(4), rng.randrange(3)]
                    self.assertEqual(h.commit(v), m.commit(v))
                    v.append("junk")
                elif op == "same":
                    self.assertFalse(h.commit(copy.deepcopy(m.states[m.idx])))
                elif op == "mutate":
                    h.current.append("x")
                elif op == "undo":
                    if m.idx == 0:
                        with self.assertRaises(IndexError):
                            h.undo()
                    else:
                        m.idx -= 1
                        self.assertEqual(h.undo(), m.states[m.idx])
                else:
                    if m.idx == len(m.states) - 1:
                        with self.assertRaises(IndexError):
                            h.redo()
                    else:
                        m.idx += 1
                        self.assertEqual(h.redo(), m.states[m.idx])
                self.assertEqual(h.current, m.states[m.idx])
                self.assertEqual(h.undo_steps, m.idx)
                self.assertEqual(h.redo_steps, len(m.states) - 1 - m.idx)
                self.assertEqual(h.can_undo, m.idx > 0)
                self.assertEqual(h.can_redo, m.idx < len(m.states) - 1)


if __name__ == "__main__":
    unittest.main()
