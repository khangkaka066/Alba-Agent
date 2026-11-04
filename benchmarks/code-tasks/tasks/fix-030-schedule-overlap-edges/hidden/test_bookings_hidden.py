import unittest

from bookings import Conflict, Schedule
from intervals import Interval, merge, overlaps

H = 60


class BookingHiddenTests(unittest.TestCase):
    def test_overlaps_truth_table(self):
        a = Interval(10, 20)
        self.assertFalse(overlaps(a, Interval(20, 30)))
        self.assertFalse(overlaps(Interval(0, 10), a))
        self.assertTrue(overlaps(a, Interval(19, 30)))
        self.assertTrue(overlaps(Interval(0, 11), a))
        self.assertTrue(overlaps(a, Interval(12, 14)))
        self.assertTrue(overlaps(Interval(0, 100), a))
        self.assertTrue(overlaps(a, a))
        self.assertFalse(overlaps(Interval(30, 40), a))

    def test_one_minute_intervals(self):
        self.assertFalse(overlaps(Interval(5, 6), Interval(6, 7)))
        self.assertTrue(overlaps(Interval(5, 6), Interval(5, 6)))

    def test_book_adjacent_on_both_sides(self):
        s = Schedule()
        s.book("mid", Interval(10 * H, 11 * H))
        s.book("before", Interval(9 * H, 10 * H))
        s.book("after", Interval(11 * H, 12 * H))
        self.assertEqual(s.names(), ["before", "mid", "after"])

    def test_conflicts_inside_and_around(self):
        s = Schedule()
        s.book("a", Interval(100, 200))
        for iv in (Interval(150, 160), Interval(50, 101), Interval(199, 300), Interval(0, 1000), Interval(100, 200)):
            with self.assertRaises(Conflict):
                s.book("x", iv)
        self.assertEqual(s.names(), ["a"])

    def test_duplicate_name_and_cancel(self):
        s = Schedule()
        s.book("a", Interval(0, 10))
        with self.assertRaises(ValueError):
            s.book("a", Interval(20, 30))
        self.assertEqual(s.cancel("a"), Interval(0, 10))
        s.book("b", Interval(5, 15))
        with self.assertRaises(KeyError):
            s.cancel("a")

    def test_free_slots_between_adjacent_bookings(self):
        s = Schedule()
        s.book("a", Interval(9 * H, 10 * H))
        s.book("b", Interval(10 * H, 11 * H))
        s.book("c", Interval(13 * H, 14 * H))
        self.assertEqual(
            s.free_slots(8 * H, 16 * H),
            [Interval(8 * H, 9 * H), Interval(11 * H, 13 * H), Interval(14 * H, 16 * H)],
        )
        self.assertEqual(s.free_slots(8 * H, 16 * H, min_length=2 * H), [Interval(11 * H, 13 * H), Interval(14 * H, 16 * H)])

    def test_free_slots_clipping_and_outside(self):
        s = Schedule()
        s.book("early", Interval(7 * H, 9 * H))
        s.book("late", Interval(17 * H, 19 * H))
        s.book("night", Interval(22 * H, 23 * H))
        self.assertEqual(s.free_slots(8 * H, 18 * H), [Interval(9 * H, 17 * H)])
        s2 = Schedule()
        s2.book("before", Interval(6 * H, 8 * H))
        s2.book("after", Interval(18 * H, 20 * H))
        self.assertEqual(s2.free_slots(8 * H, 18 * H), [Interval(8 * H, 18 * H)])

    def test_fully_booked_day(self):
        s = Schedule()
        s.book("all", Interval(8 * H, 18 * H))
        self.assertEqual(s.free_slots(8 * H, 18 * H), [])

    def test_merge_joins_touching_and_overlapping(self):
        merged = merge([Interval(10, 20), Interval(0, 5), Interval(5, 8), Interval(18, 25), Interval(30, 31)])
        self.assertEqual(merged, [Interval(0, 8), Interval(10, 25), Interval(30, 31)])
        self.assertEqual(merge([]), [])

    def test_interval_validation(self):
        with self.assertRaises(ValueError):
            Interval(5, 5)
        with self.assertRaises(ValueError):
            Interval(6, 5)
        self.assertEqual(Interval(5, 9).length, 4)


if __name__ == "__main__":
    unittest.main()
