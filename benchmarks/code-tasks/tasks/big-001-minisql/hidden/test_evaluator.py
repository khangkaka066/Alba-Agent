import unittest

from errors import SqlError
from evaluator import evaluate, matches

COL = lambda n: ("col", n)
LIT = lambda v: ("lit", v)


class EvaluatorTests(unittest.TestCase):
    def test_comparisons(self):
        row = {"a": 5, "s": "m"}
        cases = [("=", 5, True), ("!=", 5, False), ("<", 6, True), ("<=", 5, True), (">", 5, False), (">=", 6, False)]
        for op, value, expected in cases:
            self.assertIs(evaluate(("cmp", op, COL("a"), LIT(value)), row), expected, op)
        self.assertIs(evaluate(("cmp", "<", COL("s"), LIT("z")), row), True)
        self.assertIs(evaluate(("cmp", "=", LIT(2), LIT(2.0)), {}), True)

    def test_null_comparison_is_unknown(self):
        row = {"a": None}
        for op in ("=", "!=", "<", ">"):
            self.assertIsNone(evaluate(("cmp", op, COL("a"), LIT(1)), row))
        self.assertIsNone(evaluate(("cmp", "=", COL("a"), LIT(None)), row))

    def test_three_valued_and_or_not(self):
        t, f, n = ("cmp", "=", LIT(1), LIT(1)), ("cmp", "=", LIT(1), LIT(2)), ("cmp", "=", LIT(None), LIT(1))
        self.assertIs(evaluate(("and", t, t), {}), True)
        self.assertIs(evaluate(("and", f, n), {}), False)
        self.assertIs(evaluate(("and", n, f), {}), False)
        self.assertIsNone(evaluate(("and", t, n), {}))
        self.assertIs(evaluate(("or", t, n), {}), True)
        self.assertIs(evaluate(("or", n, t), {}), True)
        self.assertIsNone(evaluate(("or", f, n), {}))
        self.assertIs(evaluate(("or", f, f), {}), False)
        self.assertIsNone(evaluate(("not", n), {}))
        self.assertIs(evaluate(("not", f), {}), True)
        self.assertIs(evaluate(("not", t), {}), False)

    def test_isnull_is_never_unknown(self):
        self.assertIs(evaluate(("isnull", COL("a"), False), {"a": None}), True)
        self.assertIs(evaluate(("isnull", COL("a"), False), {"a": 0}), False)
        self.assertIs(evaluate(("isnull", COL("a"), True), {"a": None}), False)
        self.assertIs(evaluate(("isnull", COL("a"), True), {"a": ""}), True)

    def test_type_mismatch_and_unknown_column_raise(self):
        with self.assertRaises(SqlError):
            evaluate(("cmp", "=", COL("a"), LIT("x")), {"a": 1})
        with self.assertRaises(SqlError):
            evaluate(("cmp", "=", COL("missing"), LIT(1)), {"a": 1})
        with self.assertRaises(SqlError):
            evaluate(("isnull", COL("missing"), False), {"a": 1})

    def test_errors_are_raised_even_when_the_other_side_decides(self):
        bad = ("cmp", "=", COL("missing"), LIT(1))
        false = ("cmp", "=", LIT(1), LIT(2))
        with self.assertRaises(SqlError):
            evaluate(("and", false, bad), {})

    def test_matches_treats_unknown_as_no_and_none_expression_as_yes(self):
        self.assertIs(matches(None, {"a": 1}), True)
        self.assertIs(matches(("cmp", "=", COL("a"), LIT(1)), {"a": 1}), True)
        self.assertIs(matches(("cmp", "=", COL("a"), LIT(1)), {"a": None}), False)
        self.assertIs(matches(("not", ("cmp", "=", COL("a"), LIT(1))), {"a": None}), False)


if __name__ == "__main__":
    unittest.main()
