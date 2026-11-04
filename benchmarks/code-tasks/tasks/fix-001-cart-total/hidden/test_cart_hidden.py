import unittest

from cart import cart_total


class CartHiddenTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(cart_total([]), 0.0)

    def test_many_lines(self):
        self.assertEqual(cart_total([(1.5, 2), (2.25, 4), (10.0, 1)]), 22.0)

    def test_discount_with_rounding(self):
        self.assertEqual(cart_total([(19.99, 3)], 15), 50.97)

    def test_full_discount(self):
        self.assertEqual(cart_total([(5.0, 5)], 100), 0.0)

    def test_zero_quantity_line(self):
        self.assertEqual(cart_total([(9.99, 0), (3.0, 2)]), 6.0)


if __name__ == "__main__":
    unittest.main()
