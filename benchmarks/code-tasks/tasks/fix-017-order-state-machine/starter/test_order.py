import unittest

from order import Order
from workflow import InvalidTransition


class OrderTests(unittest.TestCase):
    def test_happy_path(self):
        order = Order("o1")
        for event in ("pay", "ship", "deliver"):
            order.fire(event)
        self.assertEqual(order.state, "delivered")

    def test_cancelling_a_paid_order_requires_refund(self):
        order = Order("o2")
        order.fire("pay")
        self.assertEqual(order.fire("cancel"), "refunding")
        self.assertEqual(order.fire("refund"), "cancelled")

    def test_shipped_order_cannot_be_cancelled(self):
        order = Order("o3")
        for event in ("pay", "ship"):
            order.fire(event)
        with self.assertRaises(InvalidTransition):
            order.fire("cancel")
        self.assertEqual(order.state, "shipped")


if __name__ == "__main__":
    unittest.main()
