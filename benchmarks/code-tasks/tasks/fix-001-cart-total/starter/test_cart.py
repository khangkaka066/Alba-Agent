import unittest

from cart import cart_total


class CartTests(unittest.TestCase):
    def test_quantity(self):
        self.assertEqual(cart_total([(10.0, 3)]), 30.0)

    def test_discount(self):
        self.assertEqual(cart_total([(50.0, 2)], 10), 90.0)


if __name__ == "__main__":
    unittest.main()
