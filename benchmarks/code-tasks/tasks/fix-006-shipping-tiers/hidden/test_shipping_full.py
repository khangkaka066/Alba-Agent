import unittest

from shipping import order_shipping, parcel_fee


class ShippingFullTests(unittest.TestCase):
    def test_first_tier(self):
        self.assertEqual(parcel_fee(0.1), 5.00)
        self.assertEqual(parcel_fee(1.0), 5.00)

    def test_second_tier(self):
        self.assertEqual(parcel_fee(1.01), 9.00)
        self.assertEqual(parcel_fee(5.0), 9.00)

    def test_third_tier(self):
        self.assertEqual(parcel_fee(5.01), 15.00)
        self.assertEqual(parcel_fee(20.0), 15.00)

    def test_too_heavy(self):
        with self.assertRaises(ValueError):
            parcel_fee(20.01)

    def test_non_positive(self):
        with self.assertRaises(ValueError):
            parcel_fee(0)
        with self.assertRaises(ValueError):
            parcel_fee(-2)

    def test_order_sums_parcels(self):
        self.assertEqual(order_shipping([1.0, 5.0], 20.0), 14.00)
        self.assertEqual(order_shipping([0.5, 0.5, 20.0], 10.0), 25.00)

    def test_free_shipping_threshold(self):
        self.assertEqual(order_shipping([5.0], 50.00), 0.0)
        self.assertEqual(order_shipping([5.0], 49.99), 9.00)
        self.assertEqual(order_shipping([5.0], 120.0), 0.0)

    def test_no_parcels(self):
        self.assertEqual(order_shipping([], 10.0), 0)


if __name__ == "__main__":
    unittest.main()
