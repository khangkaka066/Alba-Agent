import unittest

from inventory import OutOfStock, Stock
from reservations import ReservationBook


class ReservationHiddenTests(unittest.TestCase):
    def setUp(self):
        self.stock = Stock({"bolt": 10, "nut": 5, "gear": 1})
        self.book = ReservationBook(self.stock)

    def avail(self):
        return {sku: self.stock.available(sku) for sku in ("bolt", "nut", "gear")}

    def test_repeated_reservations_add_up(self):
        self.book.reserve("o1", "bolt", 2)
        self.book.reserve("o1", "bolt", 3)
        self.book.reserve("o1", "nut", 1)
        self.assertEqual(self.book.held("o1"), {"bolt": 5, "nut": 1})

    def test_release_returns_everything_and_is_idempotent(self):
        self.book.reserve("o1", "bolt", 2)
        self.book.reserve("o1", "bolt", 3)
        self.book.reserve("o1", "nut", 1)
        self.book.release("o1")
        self.book.release("o1")
        self.book.release("never-existed")
        self.assertEqual(self.avail(), {"bolt": 10, "nut": 5, "gear": 1})
        self.assertEqual(self.book.held("o1"), {})

    def test_commit_after_double_reserve(self):
        self.book.reserve("o1", "bolt", 4)
        self.book.reserve("o1", "bolt", 1)
        self.book.commit("o1")
        self.assertEqual(self.stock.on_hand["bolt"], 5)
        self.assertEqual(self.stock.reserved["bolt"], 0)
        self.assertEqual(self.stock.available("bolt"), 5)
        self.assertEqual(self.book.held("o1"), {})

    def test_commit_does_not_free_other_orders_holds(self):
        self.book.reserve("a", "bolt", 3)
        self.book.reserve("b", "bolt", 4)
        self.book.commit("a")
        self.assertEqual(self.stock.reserved["bolt"], 4)
        self.assertEqual(self.stock.available("bolt"), 3)
        with self.assertRaises(OutOfStock):
            self.book.reserve("c", "bolt", 4)
        self.book.reserve("c", "bolt", 3)
        self.book.release("b")
        self.assertEqual(self.stock.available("bolt"), 4)

    def test_commit_unknown_order_and_double_commit(self):
        with self.assertRaises(KeyError):
            self.book.commit("ghost")
        self.book.reserve("o", "gear", 1)
        self.book.commit("o")
        with self.assertRaises(KeyError):
            self.book.commit("o")
        self.assertEqual(self.stock.on_hand["gear"], 0)

    def test_failed_reserve_changes_nothing(self):
        self.book.reserve("o1", "nut", 4)
        before = self.avail()
        with self.assertRaises(OutOfStock):
            self.book.reserve("o1", "nut", 2)
        with self.assertRaises(ValueError):
            self.book.reserve("o1", "nut", 0)
        self.assertEqual(self.avail(), before)
        self.assertEqual(self.book.held("o1"), {"nut": 4})

    def test_reserve_many_is_all_or_nothing(self):
        before = self.avail()
        with self.assertRaises(OutOfStock):
            self.book.reserve_many("o1", {"bolt": 2, "gear": 2})
        self.assertEqual(self.avail(), before)
        self.assertEqual(self.book.held("o1"), {})
        self.book.reserve_many("o1", {"bolt": 2, "gear": 1})
        self.assertEqual(self.avail(), {"bolt": 8, "nut": 5, "gear": 0})

    def test_reserve_commit_release_cycle_keeps_counters_consistent(self):
        for n in range(1, 4):
            order = f"o{n}"
            self.book.reserve(order, "bolt", n)
            self.book.reserve(order, "bolt", 1)
        self.book.commit("o1")
        self.book.release("o2")
        self.book.commit("o3")
        self.assertEqual(self.stock.on_hand["bolt"], 10 - 2 - 4)
        self.assertEqual(self.stock.reserved["bolt"], 0)

    def test_held_returns_a_copy(self):
        self.book.reserve("o", "nut", 2)
        self.book.held("o")["nut"] = 99
        self.assertEqual(self.book.held("o"), {"nut": 2})

    def test_unknown_sku(self):
        with self.assertRaises(KeyError):
            self.book.reserve("o", "washer", 1)


if __name__ == "__main__":
    unittest.main()
