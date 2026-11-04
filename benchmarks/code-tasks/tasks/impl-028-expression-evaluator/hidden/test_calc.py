import unittest

from calc import ExprError, ExprSyntaxError, UndefinedNameError, evaluate


class ArithmeticTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(evaluate("42"), 42)
        self.assertIsInstance(evaluate("42"), int)
        self.assertEqual(evaluate("2.50"), 2.5)
        self.assertIsInstance(evaluate("3.0"), float)
        self.assertEqual(evaluate("  7  "), 7)

    def test_precedence(self):
        self.assertEqual(evaluate("2+3*4"), 14)
        self.assertEqual(evaluate("(2+3)*4"), 20)
        self.assertEqual(evaluate("2+3*4^2/8-1"), 7.0)
        self.assertEqual(evaluate("7%4*2"), 6)
        self.assertEqual(evaluate("1+2%2"), 1)

    def test_left_associativity(self):
        self.assertEqual(evaluate("10-4-3"), 3)
        self.assertEqual(evaluate("100/10/5"), 2.0)
        self.assertEqual(evaluate("2*3%4"), 2)

    def test_power(self):
        self.assertEqual(evaluate("2^10"), 1024)
        self.assertEqual(evaluate("2^3^2"), 512)
        self.assertEqual(evaluate("(2^3)^2"), 64)
        self.assertEqual(evaluate("2^-2"), 0.25)
        self.assertEqual(evaluate("2^-1"), 0.5)
        self.assertEqual(evaluate("4^0.5"), 2.0)
        self.assertEqual(evaluate("2*3^2"), 18)

    def test_unary(self):
        self.assertEqual(evaluate("-2^2"), -4)
        self.assertEqual(evaluate("(-2)^2"), 4)
        self.assertEqual(evaluate("--3"), 3)
        self.assertEqual(evaluate("+5"), 5)
        self.assertEqual(evaluate("2*-3"), -6)
        self.assertEqual(evaluate("2--3"), 5)
        self.assertEqual(evaluate("-(1+2)*3"), -9)
        self.assertEqual(evaluate("2^-3^2"), 2 ** -9)

    def test_division_and_modulo_semantics(self):
        result = evaluate("6/3")
        self.assertEqual(result, 2.0)
        self.assertIsInstance(result, float)
        self.assertEqual(evaluate("7/2"), 3.5)
        self.assertEqual(evaluate("-7%3"), 2)
        self.assertEqual(evaluate("7%-3"), -2)
        self.assertAlmostEqual(evaluate("5.5%2"), 1.5)
        self.assertIsInstance(evaluate("7%3"), int)
        self.assertIsInstance(evaluate("2*3+4"), int)


class VariableAndFunctionTests(unittest.TestCase):
    def test_variables(self):
        env = {"base": 100, "tax": 0.2, "discount": 5, "_x1": 3}
        self.assertAlmostEqual(evaluate("base * (1 + tax) - discount", env), 115.0)
        self.assertEqual(evaluate("_x1^2", env), 9)
        self.assertEqual(evaluate("base", env), 100)
        self.assertEqual(evaluate("2", None), 2)

    def test_functions(self):
        self.assertEqual(evaluate("abs(-4)"), 4)
        self.assertEqual(evaluate("abs(3-10)*2"), 14)
        self.assertEqual(evaluate("min(3, 1, 2)"), 1)
        self.assertEqual(evaluate("max(3, 1+5, 2)"), 6)
        self.assertEqual(evaluate("max(7)"), 7)
        self.assertEqual(evaluate("max(min(4, 9), abs(-2)) ^ 2"), 16)
        self.assertEqual(evaluate("min(x, y)", {"x": 5, "y": -1}), -1)

    def test_function_name_vs_variable(self):
        self.assertEqual(evaluate("max + 1", {"max": 5}), 6)
        self.assertEqual(evaluate("max(2, 8)", {"max": 5}), 8)
        with self.assertRaises(UndefinedNameError):
            evaluate("max")

    def test_undefined_names(self):
        with self.assertRaises(UndefinedNameError):
            evaluate("x + 1")
        with self.assertRaises(UndefinedNameError):
            evaluate("x + 1", {"y": 1})
        with self.assertRaises(UndefinedNameError):
            evaluate("sqrt(4)")
        with self.assertRaises(UndefinedNameError):
            evaluate("x(3)", {"x": 2})
        self.assertTrue(issubclass(UndefinedNameError, ExprError))
        self.assertTrue(issubclass(ExprError, ValueError))


class ErrorTests(unittest.TestCase):
    def test_syntax_errors(self):
        bad = [
            "", "   ", "1 +", "+", "*3", "1 2", "(1", "1)", "()", "2x", "2(3)", "(1)(2)",
            "1 + * 2", "1..2", ".5", "5.", "1.5.2", "3 $ 4", "a b", "1,2", "max()", "abs()",
            "abs(1, 2)", "min(1,)", "min(,1)", "max(1 2)", "max(1", "2 ^", "^2", "1 = 1", "1 // 2",
        ]
        for text in bad:
            with self.assertRaises(ExprSyntaxError, msg=repr(text)):
                evaluate(text, {"a": 1, "b": 2})

    def test_division_by_zero(self):
        for text in ["1/0", "1%0", "5/(3-3)", "2.5/0", "1/0.0", "0^-1", "0^-2"]:
            with self.assertRaises(ZeroDivisionError, msg=text):
                evaluate(text)

    def test_negative_base_fractional_power(self):
        with self.assertRaises(ExprError):
            evaluate("(-8)^0.5")
        with self.assertRaises(ExprError):
            evaluate("1 + (0-8)^(1/2)")
        self.assertAlmostEqual(evaluate("-8^0.5"), -(8 ** 0.5))  # unary minus applies after ^
        self.assertEqual(evaluate("(-8)^2"), 64)
        self.assertEqual(evaluate("(-8)^-1"), -0.125)

    def test_syntax_errors_take_precedence(self):
        with self.assertRaises(ExprSyntaxError):
            evaluate("1/0 + )")
        with self.assertRaises(ExprSyntaxError):
            evaluate("x + (", {})

    def test_evaluation_order_left_to_right(self):
        with self.assertRaises(UndefinedNameError):
            evaluate("x + 1/0")
        with self.assertRaises(ZeroDivisionError):
            evaluate("1/0 + x")
        with self.assertRaises(UndefinedNameError):
            evaluate("max(x, 1/0)")


if __name__ == "__main__":
    unittest.main()
