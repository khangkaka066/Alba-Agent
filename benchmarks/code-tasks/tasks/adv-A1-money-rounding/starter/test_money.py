import unittest

from money import to_cents
from invoice import line_cents


class MoneyTests(unittest.TestCase):
    def test_half_cents_round_up(self):
        self.assertEqual(to_cents(0.125), 13)
        self.assertEqual(to_cents(1.125), 113)

    def test_line(self):
        self.assertEqual(line_cents(0.125, 1), 13)


if __name__ == "__main__":
    unittest.main()
