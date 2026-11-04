import unittest

from diff import diff_lines
from lcs import lcs_table
from patch import PatchError, apply_ops, render, summarize


class PatchHiddenTests(unittest.TestCase):
    def test_pure_replacement(self):
        self.assertEqual(diff_lines(["x"], ["y"]), [("-", "x"), ("+", "y")])

    def test_multi_line_block_orders_deletions_first(self):
        ops = diff_lines(["k", "a", "b", "z"], ["k", "c", "d", "z"])
        self.assertEqual(
            ops,
            [("=", "k"), ("-", "a"), ("-", "b"), ("+", "c"), ("+", "d"), ("=", "z")],
        )

    def test_changes_in_two_separate_blocks(self):
        a = ["a", "b", "c", "d", "e"]
        b = ["a", "B", "c", "D", "e"]
        self.assertEqual(
            render(a, b), "  a\n- b\n+ B\n  c\n- d\n+ D\n  e"
        )

    def test_insert_only_and_delete_only(self):
        self.assertEqual(diff_lines([], ["a", "b"]), [("+", "a"), ("+", "b")])
        self.assertEqual(diff_lines(["a", "b"], []), [("-", "a"), ("-", "b")])
        self.assertEqual(diff_lines([], []), [])
        self.assertEqual(diff_lines(["a"], ["a"]), [("=", "a")])

    def test_trailing_changes(self):
        self.assertEqual(diff_lines(["a", "b"], ["a", "c", "d"]), [("=", "a"), ("-", "b"), ("+", "c"), ("+", "d")])

    def test_lcs_table_shape_and_values(self):
        t = lcs_table(["a", "b", "c"], ["b", "c", "d"])
        self.assertEqual(len(t), 4)
        self.assertEqual(len(t[0]), 4)
        self.assertEqual(t[0][0], 2)
        self.assertEqual(t[3], [0, 0, 0, 0])

    def test_properties_on_generated_inputs(self):
        seed = 12345
        for _ in range(60):
            lines = []
            for _ in range(2):
                size = 0
                row = []
                seed = (seed * 1103515245 + 12345) % (2**31)
                size = seed % 9
                for _ in range(size):
                    seed = (seed * 1103515245 + 12345) % (2**31)
                    row.append("abcd"[(seed >> 8) % 4])
                lines.append(row)
            a, b = lines
            ops = diff_lines(a, b)
            self.assertEqual(apply_ops(a, ops), b)
            self.assertEqual([l for o, l in ops if o in "=-"], a)
            self.assertEqual([l for o, l in ops if o in "=+"], b)
            self.assertEqual(summarize(ops)["unchanged"], lcs_table(a, b)[0][0])
            # inside a run of changes no insertion may precede a deletion
            for first, second in zip(ops, ops[1:]):
                self.assertFalse(first[0] == "+" and second[0] == "-", (a, b, ops))

    def test_apply_ops_errors(self):
        with self.assertRaises(PatchError):
            apply_ops(["a", "b"], [("=", "a")])
        with self.assertRaises(PatchError):
            apply_ops(["a"], [("-", "z")])
        with self.assertRaises(PatchError):
            apply_ops([], [("=", "a")])
        self.assertEqual(apply_ops([], [("+", "n")]), ["n"])


if __name__ == "__main__":
    unittest.main()
