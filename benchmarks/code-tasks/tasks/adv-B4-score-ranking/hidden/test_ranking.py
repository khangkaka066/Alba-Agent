import unittest

from ranking import ScoreError, rank_scores, top_n


class RankingTests(unittest.TestCase):
    def test_competition_ranking(self):
        rows = rank_scores([("a", 70), ("b", 90), ("c", 80), ("d", 80)])
        self.assertEqual([r[0] for r in rows], [1, 2, 2, 4])
        self.assertEqual([r[1] for r in rows], ["b", "c", "d", "a"])

    def test_three_way_tie_then_next(self):
        rows = rank_scores([("x", 50), ("y", 60), ("z", 60), ("w", 60), ("v", 10)])
        self.assertEqual([r[0] for r in rows], [1, 1, 1, 4, 5])

    def test_tie_order_casefold_not_ascii(self):
        rows = rank_scores([("bob", 5), ("Alice", 5), ("alan", 5), ("Zed", 5)])
        self.assertEqual([r[1] for r in rows], ["alan", "Alice", "bob", "Zed"])

    def test_full_tie_keeps_input_order(self):
        rows = rank_scores([("sam", 5), ("SAM", 5), ("Sam", 5)])
        self.assertEqual([r[1] for r in rows], ["sam", "SAM", "Sam"])

    def test_int_float_equal_and_unchanged(self):
        rows = rank_scores([("b", 90.0), ("a", 90)])
        self.assertEqual(rows, [(1, "a", 90), (1, "b", 90.0)])
        self.assertIsInstance(rows[0][2], int)
        self.assertIsInstance(rows[1][2], float)

    def test_bounds_inclusive(self):
        rows = rank_scores([("lo", 0), ("hi", 100), ("hi2", 100.0), ("lo2", 0.0)])
        self.assertEqual([r[0] for r in rows], [1, 1, 3, 3])

    def test_empty(self):
        self.assertEqual(rank_scores([]), [])
        self.assertEqual(top_n([], 3), [])

    def test_score_error_exact_type(self):
        for bad in (100.0001, 101, -0.5, -1, float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ScoreError):
                rank_scores([("ok", 50), ("bad", bad)])
            with self.assertRaises(ScoreError):
                top_n([("bad", bad)], 0)
        self.assertTrue(issubclass(ScoreError, ValueError))

    def test_type_errors(self):
        for bad in (True, False, "90", None, [1]):
            with self.assertRaises(TypeError):
                rank_scores([("a", bad)])

    def test_top_n_includes_whole_tie(self):
        data = [("a", 90), ("b", 80), ("c", 80), ("d", 80), ("e", 10)]
        self.assertEqual([r[1] for r in top_n(data, 2)], ["a", "b", "c", "d"])
        self.assertEqual([r[1] for r in top_n(data, 1)], ["a"])
        self.assertEqual([r[1] for r in top_n(data, 4)], ["a", "b", "c", "d"])
        self.assertEqual(len(top_n(data, 5)), 5)
        self.assertEqual(len(top_n(data, 100)), 5)

    def test_top_n_zero(self):
        self.assertEqual(top_n([("a", 1)], 0), [])

    def test_top_n_errors_and_order_of_validation(self):
        with self.assertRaises(ValueError):
            top_n([("a", 1)], -1)
        with self.assertRaises(TypeError):
            top_n([("a", 1)], True)
        with self.assertRaises(TypeError):
            top_n([("a", 1)], 1.0)
        with self.assertRaises(ScoreError):
            top_n([("a", 500)], -1)

    def test_input_not_modified(self):
        data = [("b", 2), ("a", 3)]
        rank_scores(data)
        self.assertEqual(data, [("b", 2), ("a", 3)])


if __name__ == "__main__":
    unittest.main()
