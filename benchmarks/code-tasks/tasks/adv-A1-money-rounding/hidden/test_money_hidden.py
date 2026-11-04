import unittest

from invoice import invoice_total, line_cents, render_total
from money import apply_rate, format_cents, to_cents


class Hidden(unittest.TestCase):
    def test_negative_half_away(self):
        self.assertEqual(to_cents(-0.125), -13)
        self.assertEqual(to_cents(-1.125), -113)
        self.assertEqual(to_cents(-0.005), -1)

    def test_positive_ties_and_float_noise(self):
        self.assertEqual(to_cents(0.005), 1)
        self.assertEqual(to_cents(2.675), 268)
        self.assertEqual(to_cents(1.005), 101)
        self.assertEqual(to_cents(19.99), 1999)
        self.assertEqual(to_cents(0.0), 0)
        self.assertEqual(to_cents(3), 300)

    def test_apply_rate_ties(self):
        self.assertEqual(apply_rate(25, 0.1), 3)
        self.assertEqual(apply_rate(-25, 0.1), -3)
        self.assertEqual(apply_rate(35, 0.1), 4)
        self.assertEqual(apply_rate(-35, 0.1), -4)
        self.assertEqual(apply_rate(1000, 0.075), 75)
        self.assertEqual(apply_rate(0, 0.2), 0)

    def test_refund_lines(self):
        self.assertEqual(line_cents(-0.125, 1), -13)
        self.assertEqual(line_cents(-2.5, 3), -750)
        self.assertEqual(invoice_total([(10.0, 1), (-0.125, 1)]), 987)

    def test_tax_on_refund_matches_tax_on_charge(self):
        charge = invoice_total([(2.5, 1)], 0.1)
        refund = invoice_total([(-2.5, 1)], 0.1)
        self.assertEqual(charge, 275)
        self.assertEqual(refund, -275)
        self.assertEqual(invoice_total([(0.25, 1)], 0.1), 28)
        self.assertEqual(invoice_total([(-0.25, 1)], 0.1), -28)

    def test_render(self):
        self.assertEqual(render_total([(-0.125, 1)]), "-0.13")
        self.assertEqual(format_cents(5), "0.05")


if __name__ == "__main__":
    unittest.main()
