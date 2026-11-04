import unittest
from decimal import Decimal

from invoice import invoice_total, line_total, split_evenly, to_cents


class InvoiceFullTests(unittest.TestCase):
    def test_to_cents_halves_up(self):
        self.assertEqual(to_cents(Decimal("0.125")), Decimal("0.13"))
        self.assertEqual(to_cents(Decimal("0.135")), Decimal("0.14"))
        self.assertEqual(to_cents(Decimal("2.675")), Decimal("2.68"))
        self.assertEqual(to_cents(Decimal("1.005")), Decimal("1.01"))

    def test_to_cents_non_halves(self):
        self.assertEqual(to_cents(Decimal("0.124")), Decimal("0.12"))
        self.assertEqual(to_cents(Decimal("0.126")), Decimal("0.13"))
        self.assertEqual(to_cents(Decimal("3")), Decimal("3.00"))

    def test_line_total(self):
        self.assertEqual(line_total("0.125", 1), Decimal("0.13"))
        self.assertEqual(line_total("19.99", 3), Decimal("59.97"))
        self.assertEqual(line_total("0.005", 3), Decimal("0.02"))
        self.assertEqual(line_total("4.00", 0), Decimal("0.00"))

    def test_invoice_totals(self):
        result = invoice_total([("0.125", 1), ("2.675", 2)], Decimal("0.10"))
        self.assertEqual(result["subtotal"], Decimal("5.48"))
        self.assertEqual(result["tax"], Decimal("0.55"))
        self.assertEqual(result["total"], Decimal("6.03"))

    def test_invoice_tax_half_cent(self):
        result = invoice_total([("1.00", 5)], Decimal("0.0250"))
        self.assertEqual(result["tax"], Decimal("0.13"))
        self.assertEqual(result["total"], Decimal("5.13"))

    def test_invoice_empty(self):
        result = invoice_total([], Decimal("0.2"))
        self.assertEqual(result["subtotal"], Decimal("0.00"))
        self.assertEqual(result["total"], Decimal("0.00"))

    def test_split_remainder_goes_to_first(self):
        shares = split_evenly(Decimal("10.00"), 3)
        self.assertEqual(shares, [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")])

    def test_split_two_leftover_cents(self):
        shares = split_evenly(Decimal("0.05"), 3)
        self.assertEqual(shares, [Decimal("0.02"), Decimal("0.02"), Decimal("0.01")])

    def test_split_even(self):
        self.assertEqual(split_evenly(Decimal("9.00"), 3), [Decimal("3.00")] * 3)

    def test_split_always_sums(self):
        for cents in (1, 7, 99, 100, 101, 1999, 10001):
            amount = Decimal(cents).scaleb(-2)
            for parties in (1, 2, 3, 4, 7):
                shares = split_evenly(amount, parties)
                self.assertEqual(len(shares), parties)
                self.assertEqual(sum(shares), amount)
                self.assertTrue(max(shares) - min(shares) <= Decimal("0.01"))

    def test_split_invalid(self):
        with self.assertRaises(ValueError):
            split_evenly(Decimal("1.00"), 0)


if __name__ == "__main__":
    unittest.main()
