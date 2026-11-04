import unittest

from stock.models import OutOfStock
from stock.report import low_stock
from stock.store import Store


class StockTests(unittest.TestCase):
    def test_cannot_reserve_what_is_already_reserved(self):
        store = Store()
        store.add_item("a", 10)
        store.reserve("a", 8)
        with self.assertRaises(OutOfStock):
            store.reserve("a", 5)

    def test_cannot_release_more_than_reserved(self):
        store = Store()
        store.add_item("a", 10)
        store.reserve("a", 2)
        with self.assertRaises(ValueError):
            store.release("a", 3)

    def test_low_stock_includes_the_threshold(self):
        store = Store()
        store.add_item("a", 3)
        store.add_item("b", 4)
        self.assertEqual(low_stock(store, 3), ["a"])


if __name__ == "__main__":
    unittest.main()
