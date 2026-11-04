import unittest

from calc import ExpressionError, evaluate


class EvaluateTests(unittest.TestCase):
    def test_numbers_and_types(self):
        self.assertEqual(evaluate("42"), 42)
        self.assertIsInstance(evaluate("42"), int)
        self.assertEqual(evaluate("1.5"), 1.5)
        self.assertIsInstance(evaluate("2.0"), float)
        self.assertEqual(evaluate("  7  "), 7)

    def test_precedence_and_associativity(self):
        self.assertEqual(evaluate("1 + 2 * 3"), 7)
        self.assertEqual(evaluate("(1 + 2) * 3"), 9)
        self.assertEqual(evaluate("10 - 4 - 3"), 3)
        self.assertEqual(evaluate("100 / 10 / 5"), 2.0)
        self.assertEqual(evaluate("2 * 3 % 4"), 2)
        self.assertEqual(evaluate("2 + 3 * 4 ** 2"), 50)

    def test_python_division_semantics(self):
        self.assertEqual(evaluate("7 / 2"), 3.5)
        self.assertEqual(evaluate("7 // 2"), 3)
        self.assertEqual(evaluate("-7 // 2"), -4)
        self.assertEqual(evaluate("-7 % 3"), 2)
        self.assertEqual(evaluate("7 % -3"), -2)
        self.assertEqual(evaluate("6 / 3"), 2.0)

    def test_power(self):
        self.assertEqual(evaluate("2 ** 10"), 1024)
        self.assertIsInstance(evaluate("2 ** 10"), int)
        self.assertEqual(evaluate("2 ** 3 ** 2"), 512)
        self.assertEqual(evaluate("(2 ** 3) ** 2"), 64)
        self.assertEqual(evaluate("-2 ** 2"), -4)
        self.assertEqual(evaluate("2 ** -1"), 0.5)
        self.assertEqual(evaluate("2 ** - 2 ** 2"), 2 ** -(2 ** 2))
        self.assertEqual(evaluate("(-2) ** 2"), 4)

    def test_unary(self):
        self.assertEqual(evaluate("-3"), -3)
        self.assertEqual(evaluate("--3"), 3)
        self.assertEqual(evaluate("+-+3"), -3)
        self.assertEqual(evaluate("4 - -2"), 6)
        self.assertEqual(evaluate("-3 * -2"), 6)
        self.assertEqual(evaluate("-(1 + 2)"), -3)

    def test_variables(self):
        self.assertEqual(evaluate("x * 2 + y", {"x": 3, "y": 0.5}), 6.5)
        self.assertEqual(evaluate("_a1 ** 2", {"_a1": 5}), 25)
        self.assertEqual(evaluate("-x", {"x": 4}), -4)
        self.assertEqual(evaluate("x", {"x": 9}), 9)

    def test_functions(self):
        self.assertEqual(evaluate("abs(-5)"), 5)
        self.assertEqual(evaluate("abs(2 - 7) * 2"), 10)
        self.assertEqual(evaluate("min(3, 1, 2)"), 1)
        self.assertEqual(evaluate("max(3)"), 3)
        self.assertEqual(evaluate("max(1, 2 * 5, min(4, 6)) + 1"), 11)
        self.assertEqual(evaluate("min(x, 10)", {"x": 4}), 4)
        self.assertEqual(evaluate("abs(abs(-2) - 5)"), 3)

    def test_division_by_zero_propagates(self):
        for expr in ("1 / 0", "1 // 0", "1 % 0", "5 / (3 - 3)"):
            with self.subTest(expr=expr):
                with self.assertRaises(ZeroDivisionError):
                    evaluate(expr)

    def test_syntax_errors(self):
        bad = ["", "   ", "1 2", "3 +", "* 3", "(1 + 2", "1 + 2)", "()", "1 +* 2", "$", "1 $ 2",
               ".5", "5.", "1..2", "1.2.3", "12abc", "2 ** ", "min(1,", "min(1 2)", "1 ,2", "(1,2)"]
        for expr in bad:
            with self.subTest(expr=expr):
                with self.assertRaises(ExpressionError):
                    evaluate(expr)

    def test_name_errors(self):
        for expr, variables in [("x", None), ("x + 1", {"y": 1}), ("foo(1)", None), ("x(1)", {"x": 2}),
                                ("abs", None), ("min", {})]:
            with self.subTest(expr=expr):
                with self.assertRaises(ExpressionError):
                    evaluate(expr, variables)

    def test_arity_errors(self):
        for expr in ("min()", "max()", "abs()", "abs(1, 2)"):
            with self.subTest(expr=expr):
                with self.assertRaises(ExpressionError):
                    evaluate(expr)

    def test_expression_error_is_value_error(self):
        self.assertTrue(issubclass(ExpressionError, ValueError))

    def test_variables_not_modified_and_optional(self):
        variables = {"a": 1}
        evaluate("a + 1", variables)
        self.assertEqual(variables, {"a": 1})
        self.assertEqual(evaluate("1 + 1", None), 2)


if __name__ == "__main__":
    unittest.main()
