import unittest

from shipping import order_shipping, parcel_fee


class ShippingTests(unittest.TestCase):
    def test_one_kg_parcel(self):
        self.assertEqual(parcel_fee(1.0), 5.00)

    def test_order_with_boundary_parcels(self):
        self.assertEqual(order_shipping([1.0, 5.0], 20.0), 14.00)


if __name__ == "__main__":
    unittest.main()
