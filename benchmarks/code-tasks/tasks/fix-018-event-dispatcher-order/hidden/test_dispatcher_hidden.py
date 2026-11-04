import unittest

from dispatcher import Dispatcher
from registry import topic_matches


class DispatcherHiddenTests(unittest.TestCase):
    def test_equal_priority_follows_subscription_order_across_kinds(self):
        d = Dispatcher()
        calls = []
        d.subscribe("x.y", lambda p: calls.append("first-wild"), priority=1)
        d.subscribe("x.*", lambda p: calls.append("second"), priority=1)
        d.subscribe("*", lambda p: calls.append("third"), priority=1)
        d.subscribe("x.y", lambda p: calls.append("fourth"), priority=1)
        d.publish("x.y")
        self.assertEqual(calls, ["first-wild", "second", "third", "fourth"])

    def test_wildcard_registered_first_wins_tie(self):
        d = Dispatcher()
        calls = []
        d.subscribe("job.*", lambda p: calls.append("wild"))
        d.subscribe("job.done", lambda p: calls.append("exact"))
        d.publish("job.done")
        self.assertEqual(calls, ["wild", "exact"])

    def test_mixed_priorities_single_order(self):
        d = Dispatcher()
        calls = []
        d.subscribe("a.b.c", lambda p: calls.append("exact-3"), priority=3)
        d.subscribe("a.*", lambda p: calls.append("wild-5"), priority=5)
        d.subscribe("*", lambda p: calls.append("all-1"), priority=1)
        d.subscribe("a.b.c", lambda p: calls.append("exact-9"), priority=9)
        d.subscribe("a.b.*", lambda p: calls.append("wild-3"), priority=3)
        d.publish("a.b.c")
        self.assertEqual(calls, ["exact-9", "wild-5", "exact-3", "wild-3", "all-1"])

    def test_results_in_call_order(self):
        d = Dispatcher()
        d.subscribe("t", lambda p: "b", priority=1)
        d.subscribe("t.*", lambda p: "a", priority=2)
        d.subscribe("t", lambda p: "c", priority=0)
        self.assertEqual(d.publish("t"), ["b", "c"])
        self.assertEqual(d.publish("t.x"), ["a"])

    def test_topic_matching_rules(self):
        self.assertTrue(topic_matches("*", "anything"))
        self.assertTrue(topic_matches("orders.*", "orders.item.added"))
        self.assertFalse(topic_matches("orders.*", "orders"))
        self.assertFalse(topic_matches("orders.*", "ordersx.created"))
        self.assertTrue(topic_matches("a.b", "a.b"))
        self.assertFalse(topic_matches("a.b", "a.b.c"))

    def test_once_with_wildcard_and_reentrant_publish(self):
        d = Dispatcher()
        calls = []

        def handler(payload):
            calls.append(payload)
            if payload == "outer":
                d.publish("e.go", "inner")

        d.subscribe("e.*", handler, once=True)
        d.publish("e.go", "outer")
        d.publish("e.go", "later")
        self.assertEqual(calls, ["outer"])

    def test_unsubscribe(self):
        d = Dispatcher()
        calls = []
        sub = d.subscribe("t", lambda p: calls.append("gone"))
        d.subscribe("t", lambda p: calls.append("kept"))
        self.assertTrue(d.unsubscribe(sub))
        self.assertFalse(d.unsubscribe(sub))
        d.publish("t")
        self.assertEqual(calls, ["kept"])

    def test_subscription_added_during_publish_waits_for_next(self):
        d = Dispatcher()
        calls = []

        def adder(payload):
            calls.append("adder")
            d.subscribe("t", lambda p: calls.append("late"))

        d.subscribe("t", adder, once=True)
        d.publish("t")
        self.assertEqual(calls, ["adder"])
        d.publish("t")
        self.assertEqual(calls, ["adder", "late"])


if __name__ == "__main__":
    unittest.main()
