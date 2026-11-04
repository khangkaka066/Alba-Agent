import unittest

from calc import run


class CalcTests(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(run("2 + 3 * 4"), "14")
        self.assertEqual(run("7 / 2"), "3.5")

    def test_float_literal(self):
        self.assertEqual(run("1.5 + 1"), "2.5")

    def test_simple_range(self):
        self.assertEqual(run("1..4"), "1,2,3,4")

    def test_range_with_expression_bounds(self):
        self.assertEqual(run("2*2..3+3"), "4,5,6")


if __name__ == "__main__":
    unittest.main()
