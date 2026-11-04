import unittest

from stock.models import OutOfStock
from stock.orders import cancel_order, place_order
from stock.report import low_stock, summary
from stock.store import Store


def make():
    store = Store()
    store.add_item("a", 10)
    store.add_item("b", 5)
    store.add_item("c", 0)
    return store


class StoreTests(unittest.TestCase):
    def test_add_item_rules(self):
        store = make()
        store.add_item("a", 5)
        self.assertEqual(store.get("a").qty, 15)
        for bad in (-1, 1.5, "3"):
            with self.assertRaises(ValueError):
                store.add_item("z", bad)
        self.assertNotIn("z", store.items)

    def test_get_unknown(self):
        with self.assertRaises(KeyError):
            make().get("nope")

    def test_reserve_uses_available(self):
        store = make()
        store.reserve("a", 8)
        self.assertEqual(store.get("a").available, 2)
        with self.assertRaises(OutOfStock):
            store.reserve("a", 3)
        self.assertEqual(store.get("a").reserved, 8)
        store.reserve("a", 2)
        self.assertEqual(store.get("a").available, 0)

    def test_reserve_argument_errors(self):
        store = make()
        for bad in (0, -1, 1.0):
            with self.assertRaises(ValueError):
                store.reserve("a", bad)
        with self.assertRaises(KeyError):
            store.reserve("nope", 1)
        self.assertEqual(store.get("a").reserved, 0)

    def test_release(self):
        store = make()
        store.reserve("a", 4)
        store.release("a", 3)
        self.assertEqual(store.get("a").reserved, 1)
        with self.assertRaises(ValueError):
            store.release("a", 2)
        self.assertEqual(store.get("a").reserved, 1)
        with self.assertRaises(ValueError):
            store.release("a", 0)

    def test_commit(self):
        store = make()
        store.reserve("a", 4)
        store.commit("a", 3)
        item = store.get("a")
        self.assertEqual((item.qty, item.reserved, item.available), (7, 1, 6))
        with self.assertRaises(ValueError):
            store.commit("a", 2)
        self.assertEqual((item.qty, item.reserved), (7, 1))


class OrderTests(unittest.TestCase):
    def test_success_and_cancel(self):
        store = make()
        lines = [("a", 3), ("b", 2), ("a", 1)]
        place_order(store, lines)
        self.assertEqual((store.get("a").reserved, store.get("b").reserved), (4, 2))
        cancel_order(store, lines)
        self.assertEqual((store.get("a").reserved, store.get("b").reserved), (0, 0))

    def test_out_of_stock_rolls_everything_back(self):
        store = make()
        store.reserve("b", 1)
        with self.assertRaises(OutOfStock):
            place_order(store, [("a", 4), ("b", 4), ("b", 1)])
        self.assertEqual((store.get("a").reserved, store.get("b").reserved), (0, 1))

    def test_duplicate_lines_count_together(self):
        store = make()
        with self.assertRaises(OutOfStock):
            place_order(store, [("b", 3), ("b", 3)])
        self.assertEqual(store.get("b").reserved, 0)

    def test_unknown_sku_changes_nothing(self):
        store = make()
        with self.assertRaises(KeyError) as caught:
            place_order(store, [("a", 1), ("ghost", 1)])
        self.assertEqual(caught.exception.args, ("ghost",))
        self.assertEqual(store.get("a").reserved, 0)

    def test_bad_quantity_rolls_back(self):
        store = make()
        with self.assertRaises(ValueError):
            place_order(store, [("a", 2), ("b", 0)])
        self.assertEqual(store.get("a").reserved, 0)

    def test_empty_order(self):
        with self.assertRaises(ValueError):
            place_order(make(), [])


class ReportTests(unittest.TestCase):
    def test_low_stock_is_inclusive_and_uses_available(self):
        store = make()
        store.reserve("a", 7)
        self.assertEqual(low_stock(store, 3), ["a", "c"])
        self.assertEqual(low_stock(store, 5), ["a", "b", "c"])
        self.assertEqual(low_stock(store, -1), [])

    def test_summary(self):
        store = make()
        store.reserve("b", 2)
        self.assertEqual(summary(store), ["a 10 0 10", "b 5 2 3", "c 0 0 0"])
        self.assertEqual(summary(Store()), [])


if __name__ == "__main__":
    unittest.main()
