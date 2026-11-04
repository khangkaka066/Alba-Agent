import unittest

from inventory import OutOfStock, Stock
from reservations import ReservationBook


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.stock = Stock({"bolt": 10, "nut": 5})
        self.book = ReservationBook(self.stock)

    def test_release_restores_availability_after_two_reservations(self):
        self.book.reserve("o1", "bolt", 3)
        self.book.reserve("o1", "bolt", 4)
        self.assertEqual(self.stock.available("bolt"), 3)
        self.book.release("o1")
        self.assertEqual(self.stock.available("bolt"), 10)

    def test_commit_removes_stock_for_good(self):
        self.book.reserve("o2", "nut", 2)
        self.book.commit("o2")
        self.assertEqual(self.stock.on_hand["nut"], 3)
        self.assertEqual(self.stock.available("nut"), 3)

    def test_cannot_reserve_more_than_available(self):
        self.book.reserve("o3", "nut", 4)
        with self.assertRaises(OutOfStock):
            self.book.reserve("o4", "nut", 2)
        self.assertEqual(self.stock.available("nut"), 1)


if __name__ == "__main__":
    unittest.main()
