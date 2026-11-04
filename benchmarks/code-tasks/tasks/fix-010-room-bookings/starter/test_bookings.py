import unittest
from datetime import date

from bookings import has_conflict, occupied_dates


class BookingTests(unittest.TestCase):
    def test_back_to_back_is_fine(self):
        existing = [(date(2025, 3, 1), date(2025, 3, 4))]
        self.assertFalse(has_conflict(existing, date(2025, 3, 4), date(2025, 3, 6)))

    def test_occupied_dates(self):
        got = occupied_dates(date(2025, 3, 1), date(2025, 3, 3))
        self.assertEqual(got, {date(2025, 3, 1), date(2025, 3, 2)})


if __name__ == "__main__":
    unittest.main()
