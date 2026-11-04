import unittest

from fulfilment import ship_now, shortages


class FulfilmentTests(unittest.TestCase):
    def test_all_shortages_reported(self):
        order = {"a": 5, "b": 3, "c": 2}
        stock = {"a": 1, "b": 0, "c": 2}
        self.assertEqual(shortages(order, stock), {"a": 4, "b": 3})

    def test_ship_now(self):
        order = {"a": 5, "b": 3, "c": 2}
        stock = {"a": 1, "b": 0, "c": 1}
        self.assertEqual(ship_now(order, stock), {"a": 1, "c": 1})


if __name__ == "__main__":
    unittest.main()
