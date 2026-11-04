import unittest

from fulfilment import can_fulfil, ship_now, shortages


class FulfilmentFullTests(unittest.TestCase):
    def test_all_shortages_reported(self):
        order = {"a": 5, "b": 3, "c": 2}
        stock = {"a": 1, "b": 0, "c": 2}
        self.assertEqual(shortages(order, stock), {"a": 4, "b": 3})

    def test_shortage_only_in_last_item(self):
        self.assertEqual(shortages({"a": 1, "b": 1, "c": 9}, {"a": 1, "b": 1, "c": 4}), {"c": 5})

    def test_missing_sku_counts_as_zero(self):
        self.assertEqual(shortages({"x": 2, "y": 1}, {}), {"x": 2, "y": 1})

    def test_no_shortage(self):
        self.assertEqual(shortages({"a": 2}, {"a": 2, "b": 5}), {})
        self.assertEqual(shortages({}, {"a": 1}), {})

    def test_ship_now(self):
        order = {"a": 5, "b": 3, "c": 2}
        stock = {"a": 1, "b": 0, "c": 1}
        self.assertEqual(ship_now(order, stock), {"a": 1, "c": 1})

    def test_ship_now_later_items_fully_covered(self):
        order = {"a": 5, "b": 3, "c": 2, "d": 4}
        stock = {"a": 2, "b": 3, "c": 0, "d": 10}
        self.assertEqual(ship_now(order, stock), {"a": 2, "b": 3, "d": 4})

    def test_ship_now_nothing(self):
        self.assertEqual(ship_now({"a": 1}, {}), {})

    def test_can_fulfil(self):
        self.assertTrue(can_fulfil({"a": 1}, {"a": 1}))
        self.assertFalse(can_fulfil({"a": 1, "b": 1}, {"a": 1}))
        self.assertTrue(can_fulfil({}, {}))

    def test_inputs_untouched(self):
        order = {"a": 2, "b": 2}
        stock = {"a": 1}
        shortages(order, stock)
        ship_now(order, stock)
        self.assertEqual(order, {"a": 2, "b": 2})
        self.assertEqual(stock, {"a": 1})


if __name__ == "__main__":
    unittest.main()
