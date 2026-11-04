import unittest

from bookings import Conflict, Schedule
from intervals import Interval

H = 60


class BookingTests(unittest.TestCase):
    def test_back_to_back_meetings_are_fine(self):
        s = Schedule()
        s.book("standup", Interval(9 * H, 10 * H))
        s.book("review", Interval(10 * H, 11 * H))
        self.assertEqual(s.names(), ["standup", "review"])

    def test_real_overlap_is_refused(self):
        s = Schedule()
        s.book("a", Interval(9 * H, 10 * H))
        with self.assertRaises(Conflict):
            s.book("b", Interval(9 * H + 30, 10 * H + 30))

    def test_free_slots(self):
        s = Schedule()
        s.book("a", Interval(9 * H, 10 * H))
        self.assertEqual(s.free_slots(8 * H, 12 * H), [Interval(8 * H, 9 * H), Interval(10 * H, 12 * H)])


if __name__ == "__main__":
    unittest.main()
