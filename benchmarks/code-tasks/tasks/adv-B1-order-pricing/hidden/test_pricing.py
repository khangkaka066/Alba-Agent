import unittest

from pricing import price_order


def p(items, tax="0", coupon=None):
    return price_order(items, tax, coupon)


class PricingTests(unittest.TestCase):
    def test_half_even_line(self):
        self.assertEqual(p([("0.125", 1)])["subtotal"], "0.12")
        self.assertEqual(p([("0.135", 1)])["subtotal"], "0.14")
        self.assertEqual(p([("2.675", 1)])["subtotal"], "2.68")
        self.assertEqual(p([("0.005", 1)])["subtotal"], "0.00")
        self.assertEqual(p([("0.015", 1)])["subtotal"], "0.02")
        self.assertEqual(p([("0.0251", 1)])["subtotal"], "0.03")

    def test_quantity_multiplied_before_rounding(self):
        self.assertEqual(p([("0.125", 3)])["subtotal"], "0.38")  # 0.375 -> 0.38

    def test_tax_half_even_per_line(self):
        r = p([("0.50", 1), ("0.50", 1)], tax="5")
        self.assertEqual(r["tax"], "0.04")  # 0.025 -> 0.02 each, not 0.05 on the sum
        self.assertEqual(r["total"], "1.04")
        self.assertEqual(p([("0.70", 1)], tax="5")["tax"], "0.04")  # 0.035 -> 0.04

    def test_coupon_per_line_then_tax_on_discounted(self):
        r = p([("0.25", 1), ("0.25", 1)], tax="10", coupon="50")
        self.assertEqual(r["subtotal"], "0.50")
        self.assertEqual(r["discount"], "0.24")  # 0.125 -> 0.12 each
        self.assertEqual(r["tax"], "0.02")  # 0.13 * 10% = 0.013 -> 0.01 each
        self.assertEqual(r["total"], "0.28")

    def test_discount_half_even_up_case(self):
        r = p([("0.30", 1)], coupon="25")  # 0.075 -> 0.08
        self.assertEqual(r["discount"], "0.08")
        self.assertEqual(r["total"], "0.22")

    def test_zero_coupon_valid_and_none(self):
        self.assertEqual(p([("1.00", 2)], coupon="0")["discount"], "0.00")
        self.assertEqual(p([("1.00", 2)], coupon=None)["total"], "2.00")
        self.assertEqual(p([("1.00", 2)], coupon="100")["total"], "0.00")

    def test_empty_items(self):
        self.assertEqual(p([]), {"subtotal": "0.00", "discount": "0.00", "tax": "0.00", "total": "0.00"})
        self.assertEqual(p([], tax="8.25", coupon="10")["total"], "0.00")

    def test_format_two_places(self):
        r = p([("10", 1)], tax="8.25")
        self.assertEqual(r, {"subtotal": "10.00", "discount": "0.00", "tax": "0.82", "total": "10.82"})

    def test_value_errors(self):
        bad = [
            lambda: p([("1.00", 1)], coupon=""),
            lambda: p([("1.00", 1)], coupon="101"),
            lambda: p([("1.00", 1)], coupon="-1"),
            lambda: p([("1.00", 1)], tax="100.01"),
            lambda: p([("1.00", 1)], tax="abc"),
            lambda: p([("1.00", 1)], tax=""),
            lambda: p([("-1.00", 1)]),
            lambda: p([("abc", 1)]),
            lambda: p([("1.00", 0)]),
            lambda: p([("1.00", True)]),
            lambda: p([("1.00", 1.0)]),
            lambda: p([("NaN", 1)]),
        ]
        for call in bad:
            with self.assertRaises(ValueError):
                call()

    def test_type_errors(self):
        with self.assertRaises(TypeError):
            price_order(None, "5")
        with self.assertRaises(TypeError):
            price_order([], None)


if __name__ == "__main__":
    unittest.main()
