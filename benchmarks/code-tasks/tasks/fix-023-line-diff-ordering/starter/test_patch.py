import unittest

from diff import diff_lines
from patch import apply_ops, render, summarize


class PatchTests(unittest.TestCase):
    def test_replace_one_line(self):
        self.assertEqual(render(["a", "b", "c"], ["a", "x", "c"]), "  a\n- b\n+ x\n  c")

    def test_roundtrip(self):
        a = ["one", "two", "three", "four"]
        b = ["one", "three", "five", "four", "six"]
        self.assertEqual(apply_ops(a, diff_lines(a, b)), b)

    def test_summary(self):
        ops = diff_lines(["a", "b"], ["b", "c"])
        self.assertEqual(summarize(ops), {"added": 1, "removed": 1, "unchanged": 1})


if __name__ == "__main__":
    unittest.main()
