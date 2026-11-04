import unittest
from datetime import datetime, timezone

from tz import parse_ts, to_utc, utc_offset_minutes
from window import minutes_between, overlaps, utc_date


def u(*a):
    return datetime(*a, tzinfo=timezone.utc)


class Hidden(unittest.TestCase):
    def test_half_hour_offsets(self):
        self.assertEqual(parse_ts("2024-03-01T10:00:00-03:30"), u(2024, 3, 1, 13, 30))
        self.assertEqual(parse_ts("2024-03-01T10:00:00+05:30"), u(2024, 3, 1, 4, 30))
        self.assertEqual(parse_ts("2024-03-01T10:00:00+05:45"), u(2024, 3, 1, 4, 15))
        self.assertEqual(utc_offset_minutes(datetime.fromisoformat("2024-01-01T00:00:00-03:30")), -210)
        self.assertEqual(utc_offset_minutes(datetime.fromisoformat("2024-01-01T00:00:00+05:30")), 330)

    def test_naive_and_zero_and_z(self):
        self.assertEqual(parse_ts("2024-03-01T10:00:00"), u(2024, 3, 1, 10, 0))
        self.assertEqual(parse_ts("2024-03-01T10:00:00+00:00"), u(2024, 3, 1, 10, 0))
        self.assertEqual(parse_ts("2024-03-01T10:00:00Z"), u(2024, 3, 1, 10, 0))
        self.assertEqual(utc_offset_minutes(datetime(2024, 1, 1)), 0)
        self.assertEqual(to_utc(datetime(2024, 1, 1, 5)), u(2024, 1, 1, 5))

    def test_result_is_aware_utc(self):
        for s in ("2024-03-01T10:00:00", "2024-03-01T10:00:00-08:00", "2024-03-01T10:00:00+09:00"):
            self.assertEqual(parse_ts(s).utcoffset().total_seconds(), 0)

    def test_date_rollover(self):
        self.assertEqual(parse_ts("2024-12-31T22:00:00-05:00"), u(2025, 1, 1, 3, 0))
        self.assertEqual(utc_date("2024-12-31T22:00:00-05:00"), "2025-01-01")
        self.assertEqual(utc_date("2024-01-01T01:00:00+09:00"), "2023-12-31")
        self.assertEqual(utc_date("2024-02-29T23:59:00"), "2024-02-29")

    def test_minutes_between(self):
        self.assertEqual(minutes_between("2024-03-01T10:00:00+05:30", "2024-03-01T10:00:00Z"), 330)
        self.assertEqual(minutes_between("2024-03-01T10:00:00", "2024-03-01T09:00:00"), -60)
        self.assertEqual(minutes_between("2024-03-01T10:00:00-03:30", "2024-03-01T10:00:00+05:30"), -540)

    def test_overlaps(self):
        a = ("2024-03-01T10:00:00-05:00", "2024-03-01T11:00:00-05:00")  # 15:00-16:00Z
        b = ("2024-03-01T16:00:00+00:00", "2024-03-01T17:00:00+00:00")  # touches only
        c = ("2024-03-01T20:30:00+05:30", "2024-03-01T22:00:00+05:30")  # 15:00-16:30Z
        self.assertFalse(overlaps(a, b))
        self.assertTrue(overlaps(a, c))
        self.assertTrue(overlaps(c, b))


if __name__ == "__main__":
    unittest.main()
