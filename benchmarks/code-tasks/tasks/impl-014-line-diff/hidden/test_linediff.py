import itertools
import unittest

from linediff import diff_lines, diff_stats, render_diff


def lcs_len(a, b):
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            table[i + 1][j + 1] = table[i][j] + 1 if x == y else max(table[i][j + 1], table[i + 1][j])
    return table[len(a)][len(b)]


class DiffInvariantMixin:
    def check(self, old, new):
        old_copy, new_copy = list(old), list(new)
        ops = diff_lines(old, new)
        self.assertEqual(old, old_copy)
        self.assertEqual(new, new_copy)
        for item in ops:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
            self.assertIn(item[0], "=-+")
        self.assertEqual([l for op, l in ops if op != "+"], old)
        self.assertEqual([l for op, l in ops if op != "-"], new)
        self.assertEqual(sum(1 for op, _ in ops if op == "="), lcs_len(old, new))
        for (op1, _), (op2, _) in zip(ops, ops[1:]):
            self.assertFalse(op1 == "+" and op2 == "-", f"'+' followed by '-' in {ops}")
        return ops


class DiffTests(DiffInvariantMixin, unittest.TestCase):
    def test_empty_cases(self):
        self.assertEqual(diff_lines([], []), [])
        self.assertEqual(diff_lines([], ["x"]), [("+", "x")])
        self.assertEqual(diff_lines(["x", "y"], []), [("-", "x"), ("-", "y")])

    def test_identical(self):
        self.assertEqual(diff_lines(["a", "b"], ["a", "b"]), [("=", "a"), ("=", "b")])

    def test_single_change(self):
        self.assertEqual(
            diff_lines(["a", "b", "c"], ["a", "x", "c"]),
            [("=", "a"), ("-", "b"), ("+", "x"), ("=", "c")],
        )

    def test_pure_insert_and_delete(self):
        self.assertEqual(diff_lines(["a", "c"], ["a", "b", "c"]), [("=", "a"), ("+", "b"), ("=", "c")])
        self.assertEqual(diff_lines(["a", "b", "c"], ["a", "c"]), [("=", "a"), ("-", "b"), ("=", "c")])

    def test_unique_lcs_with_multi_line_hunks(self):
        old = ["h1", "old1", "old2", "mid", "tail"]
        new = ["h1", "new1", "mid", "new2", "new3", "tail"]
        self.assertEqual(
            diff_lines(old, new),
            [("=", "h1"), ("-", "old1"), ("-", "old2"), ("+", "new1"), ("=", "mid"),
             ("+", "new2"), ("+", "new3"), ("=", "tail")],
        )

    def test_completely_different(self):
        self.assertEqual(diff_lines(["a", "b"], ["c"]), [("-", "a"), ("-", "b"), ("+", "c")])

    def test_blank_and_space_lines_are_opaque(self):
        ops = self.check(["", "a b", " "], ["a b", "", " ", ""])
        self.assertEqual(sum(1 for op, _ in ops if op == "="), 2)

    def test_ambiguous_case_satisfies_invariants(self):
        ops = self.check(["a", "b"], ["b", "a"])
        self.assertEqual(sum(1 for op, _ in ops if op == "="), 1)

    def test_invariants_on_many_small_inputs(self):
        alphabet = "abc"
        seqs = [list(p) for n in range(0, 5) for p in itertools.product(alphabet, repeat=n)]
        for old in seqs[::7]:
            for new in seqs[::5]:
                self.check(old, new)

    def test_repeated_lines(self):
        ops = self.check(["x", "x", "y", "x"], ["x", "y", "x", "x"])
        self.assertEqual(sum(1 for op, _ in ops if op == "="), 3)


class RenderTests(unittest.TestCase):
    def test_render(self):
        ops = [("=", "a"), ("-", "b"), ("+", "x y"), ("=", "")]
        self.assertEqual(render_diff(ops), "  a\n- b\n+ x y\n  ")

    def test_render_empty(self):
        self.assertEqual(render_diff([]), "")

    def test_render_unknown_op(self):
        with self.assertRaises(ValueError):
            render_diff([("?", "a")])

    def test_render_of_real_diff(self):
        self.assertEqual(
            render_diff(diff_lines(["a", "b"], ["a", "c", "d"])),
            "  a\n- b\n+ c\n+ d",
        )


class StatsTests(unittest.TestCase):
    def test_stats(self):
        self.assertEqual(diff_stats([]), (0, 0))
        self.assertEqual(diff_stats([("=", "a"), ("-", "b"), ("-", "c"), ("+", "d")]), (1, 2))
        self.assertEqual(diff_stats(diff_lines(["a", "b", "c"], ["a", "x", "y", "c", "z"])), (3, 1))

    def test_stats_unknown_op(self):
        with self.assertRaises(ValueError):
            diff_stats([("=", "a"), ("*", "b")])


if __name__ == "__main__":
    unittest.main()
