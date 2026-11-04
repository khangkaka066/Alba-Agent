import unittest
from decimal import Decimal

from invoice import invoice_total, line_total, split_evenly


class InvoiceTests(unittest.TestCase):
    def test_half_cent_rounds_up(self):
        self.assertEqual(line_total("0.125", 1), Decimal("0.13"))

    def test_invoice(self):
        result = invoice_total([("0.125", 1), ("2.675", 2)], Decimal("0.10"))
        self.assertEqual(result["subtotal"], Decimal("5.48"))
        self.assertEqual(result["tax"], Decimal("0.55"))
        self.assertEqual(result["total"], Decimal("6.03"))

    def test_split_keeps_every_cent(self):
        shares = split_evenly(Decimal("10.00"), 3)
        self.assertEqual(shares, [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")])


if __name__ == "__main__":
    unittest.main()
