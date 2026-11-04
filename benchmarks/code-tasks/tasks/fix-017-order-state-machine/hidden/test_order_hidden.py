import unittest

from order import Order
from workflow import InvalidTransition, Machine


class OrderHiddenTests(unittest.TestCase):
    def test_new_order_cancels_directly(self):
        order = Order("a")
        self.assertEqual(order.fire("cancel"), "cancelled")

    def test_paid_cancel_then_refund_history(self):
        order = Order("b")
        order.fire("pay")
        order.fire("cancel")
        order.fire("refund")
        self.assertEqual(
            order.history,
            [("new", "pay", "paid"), ("paid", "cancel", "refunding"), ("refunding", "refund", "cancelled")],
        )

    def test_delivered_and_cancelled_cannot_cancel(self):
        order = Order("c")
        for event in ("pay", "ship", "deliver"):
            order.fire(event)
        self.assertFalse(order.can("cancel"))
        with self.assertRaises(InvalidTransition):
            order.fire("cancel")
        gone = Order("d")
        gone.fire("cancel")
        with self.assertRaises(InvalidTransition):
            gone.fire("cancel")
        self.assertEqual(gone.history, [("new", "cancel", "cancelled")])

    def test_invalid_event_leaves_state_and_history(self):
        order = Order("e")
        with self.assertRaises(InvalidTransition):
            order.fire("ship")
        self.assertEqual(order.state, "new")
        self.assertEqual(order.history, [])

    def test_allowed_events_by_state(self):
        order = Order("f")
        self.assertEqual(order.machine.allowed_events("new"), ["cancel", "pay"])
        self.assertEqual(order.machine.allowed_events("paid"), ["cancel", "ship"])
        self.assertEqual(order.machine.allowed_events("shipped"), ["deliver"])
        self.assertEqual(order.machine.allowed_events("delivered"), [])
        self.assertEqual(order.machine.allowed_events("cancelled"), [])

    def test_custom_machine_specific_beats_wildcard(self):
        machine = Machine(
            {("*", "reset"): "idle", ("busy", "reset"): "draining", ("idle", "start"): "busy", ("draining", "reset"): None},
            initial="idle",
        )
        self.assertEqual(machine.lookup("busy", "reset"), "draining")
        self.assertEqual(machine.lookup("idle", "reset"), "idle")
        self.assertEqual(machine.lookup("anything", "reset"), "idle")
        self.assertIsNone(machine.lookup("draining", "reset"))
        self.assertIsNone(machine.lookup("busy", "start"))

    def test_wildcard_only_for_its_event(self):
        machine = Machine({("*", "ping"): "pong"}, initial="x")
        order = Order("g", machine)
        self.assertTrue(order.can("ping"))
        self.assertFalse(order.can("pong"))


if __name__ == "__main__":
    unittest.main()
