import unittest
from datetime import date

from bookings import free_dates, has_conflict, nights, occupied_dates


def d(day, month=3):
    return date(2025, month, day)


class BookingsFullTests(unittest.TestCase):
    def test_nights(self):
        self.assertEqual(nights(d(1), d(4)), 3)
        self.assertEqual(nights(d(28, 2), d(2)), 2)
        with self.assertRaises(ValueError):
            nights(d(4), d(4))
        with self.assertRaises(ValueError):
            nights(d(5), d(4))

    def test_occupied_dates(self):
        self.assertEqual(occupied_dates(d(1), d(3)), {d(1), d(2)})
        self.assertEqual(occupied_dates(d(31), d(2, 4)), {d(31), d(1, 4)})
        self.assertEqual(len(occupied_dates(d(1), d(8))), 7)

    def test_back_to_back_after(self):
        self.assertFalse(has_conflict([(d(1), d(4))], d(4), d(6)))

    def test_back_to_back_before(self):
        self.assertFalse(has_conflict([(d(4), d(6))], d(1), d(4)))

    def test_overlap_detected(self):
        self.assertTrue(has_conflict([(d(1), d(4))], d(3), d(6)))
        self.assertTrue(has_conflict([(d(3), d(6))], d(1), d(4)))

    def test_contained_and_identical(self):
        self.assertTrue(has_conflict([(d(1), d(10))], d(3), d(5)))
        self.assertTrue(has_conflict([(d(3), d(5))], d(1), d(10)))
        self.assertTrue(has_conflict([(d(3), d(5))], d(3), d(5)))

    def test_one_night_stays(self):
        self.assertFalse(has_conflict([(d(3), d(4))], d(4), d(5)))
        self.assertTrue(has_conflict([(d(3), d(4))], d(3), d(4)))

    def test_no_bookings(self):
        self.assertFalse(has_conflict([], d(1), d(2)))

    def test_multiple_bookings(self):
        existing = [(d(1), d(3)), (d(5), d(8))]
        self.assertFalse(has_conflict(existing, d(3), d(5)))
        self.assertTrue(has_conflict(existing, d(2), d(4)))

    def test_free_dates(self):
        existing = [(d(2), d(4)), (d(6), d(7))]
        self.assertEqual(free_dates(existing, d(1), d(8)), [d(1), d(4), d(5), d(7)])
        self.assertEqual(free_dates([], d(1), d(3)), [d(1), d(2)])


if __name__ == "__main__":
    unittest.main()
