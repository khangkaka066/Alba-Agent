import unittest

from leaderboard import top
from report import rank_rows, render


class Hidden(unittest.TestCase):
    def test_ties_not_alphabetical(self):
        entries = [("zed", 5), ("amy", 5), ("mid", 5)]
        self.assertEqual(top(entries, 3), entries)

    def test_ties_mixed(self):
        entries = [("zed", 3), ("yan", 8), ("amy", 8), ("bob", 3), ("xi", 8)]
        self.assertEqual(
            top(entries, 5),
            [("yan", 8), ("amy", 8), ("xi", 8), ("zed", 3), ("bob", 3)],
        )

    def test_cut_inside_a_tie_group_keeps_earliest(self):
        entries = [("zed", 5), ("amy", 5), ("bob", 5)]
        self.assertEqual(top(entries, 2), [("zed", 5), ("amy", 5)])

    def test_float_and_negative_scores(self):
        entries = [("b", -1.5), ("a", 2.25), ("c", -1.5), ("d", 2.25)]
        self.assertEqual(top(entries, 4), [("a", 2.25), ("d", 2.25), ("b", -1.5), ("c", -1.5)])

    def test_n_bounds_and_input_untouched(self):
        entries = [("b", 1), ("a", 2)]
        self.assertEqual(top(entries, 0), [])
        self.assertEqual(top(entries, 10), [("a", 2), ("b", 1)])
        self.assertEqual(entries, [("b", 1), ("a", 2)])
        self.assertEqual(top([], 3), [])

    def test_report_competition_ranking(self):
        entries = [("zed", 7), ("amy", 9), ("bob", 7), ("cat", 7), ("dan", 1)]
        self.assertEqual(
            rank_rows(entries, 5),
            [(1, "amy", 9), (2, "zed", 7), (2, "bob", 7), (2, "cat", 7), (5, "dan", 1)],
        )

    def test_render(self):
        self.assertEqual(render([("zed", 2), ("amy", 2)], 2), "1. zed (2)\n1. amy (2)")


if __name__ == "__main__":
    unittest.main()
