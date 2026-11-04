import unittest
from datetime import datetime, timezone

from tz import parse_ts
from window import minutes_between


class TzTests(unittest.TestCase):
    def test_negative_offset(self):
        self.assertEqual(parse_ts("2024-03-01T10:00:00-05:00"), datetime(2024, 3, 1, 15, 0, tzinfo=timezone.utc))

    def test_minutes_between_mixed_offsets(self):
        self.assertEqual(minutes_between("2024-03-01T10:00:00-05:00", "2024-03-01T16:00:00+00:00"), 60)


if __name__ == "__main__":
    unittest.main()
