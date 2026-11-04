import unittest

from dispatcher import Dispatcher


class DispatcherTests(unittest.TestCase):
    def test_priority_then_subscription_order(self):
        d = Dispatcher()
        calls = []
        d.subscribe("a.b", lambda p: calls.append("low"), priority=0)
        d.subscribe("a.b", lambda p: calls.append("high"), priority=5)
        d.subscribe("a.b", lambda p: calls.append("low2"), priority=0)
        d.publish("a.b")
        self.assertEqual(calls, ["high", "low", "low2"])

    def test_wildcard_with_higher_priority_runs_first(self):
        d = Dispatcher()
        calls = []
        d.subscribe("orders.created", lambda p: calls.append("exact"), priority=0)
        d.subscribe("orders.*", lambda p: calls.append("wild"), priority=10)
        d.publish("orders.created")
        self.assertEqual(calls, ["wild", "exact"])

    def test_once_runs_a_single_time(self):
        d = Dispatcher()
        calls = []
        d.subscribe("t", lambda p: calls.append(p), once=True)
        d.publish("t", 1)
        d.publish("t", 2)
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
