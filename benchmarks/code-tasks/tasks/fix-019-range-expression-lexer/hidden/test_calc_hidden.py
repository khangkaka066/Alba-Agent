import unittest

from calc import run
from parser import ParseError, evaluate
from tokenizer import TokenError, tokenize


class CalcHiddenTests(unittest.TestCase):
    def test_tokens_for_int_dotdot_int(self):
        self.assertEqual(tokenize("1..5"), [("int", 1), ("op", ".."), ("int", 5)])

    def test_tokens_for_float_then_range(self):
        self.assertEqual(tokenize("1.5..7"), [("float", 1.5), ("op", ".."), ("int", 7)])
        self.assertEqual(tokenize("10 .. 12"), [("int", 10), ("op", ".."), ("int", 12)])

    def test_no_spaces_range_with_negative_bound(self):
        self.assertEqual(run("-2..2"), "-2,-1,0,1,2")
        self.assertEqual(run("0..-1"), "")

    def test_range_single_element_and_big(self):
        self.assertEqual(run("5..5"), "5")
        self.assertEqual(evaluate("1..100")[-1], 100)
        self.assertEqual(len(evaluate("1..100")), 100)

    def test_range_in_parentheses_and_nested_expression(self):
        self.assertEqual(run("(1+1)..(2*3)"), "2,3,4,5,6")
        self.assertEqual(run("(1..3)"), "1,2,3")

    def test_float_range_bounds_rejected(self):
        self.assertTrue(run("1.5..4").startswith("error:"))
        self.assertTrue(run("1..4.5").startswith("error:"))
        self.assertTrue(run("1/1..3").startswith("error:"))

    def test_floats_still_work(self):
        self.assertEqual(run("0.25 * 4"), "1.0")
        self.assertEqual(run("10.5 - 0.5"), "10.0")
        self.assertEqual(tokenize("3.14"), [("float", 3.14)])

    def test_trailing_dot_is_an_error(self):
        with self.assertRaises(TokenError):
            tokenize("1.")
        self.assertTrue(run("2 + 1.").startswith("error:"))

    def test_errors(self):
        self.assertTrue(run("2 +").startswith("error:"))
        self.assertTrue(run("(1+2").startswith("error:"))
        self.assertTrue(run("1 $ 2").startswith("error:"))
        with self.assertRaises(ParseError):
            evaluate("1 2")


if __name__ == "__main__":
    unittest.main()
