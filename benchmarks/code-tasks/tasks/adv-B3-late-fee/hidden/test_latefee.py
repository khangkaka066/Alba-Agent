import unittest

from latefee import late_fee


class LateFeeTests(unittest.TestCase):
    def test_grace_inclusive(self):
        # 2024-01-15 is a Monday
        self.assertEqual(late_fee("2024-01-15", "2024-01-20", 100), 0)  # +5
        self.assertEqual(late_fee("2024-01-15", "2024-01-21", 100), 100)  # +6
        self.assertEqual(late_fee("2024-01-15", "2024-01-22", 100), 200)

    def test_on_time_and_early(self):
        self.assertEqual(late_fee("2024-01-15", "2024-01-15", 100), 0)
        self.assertEqual(late_fee("2024-01-15", "2023-12-01", 100), 0)

    def test_weekend_due_moves_to_monday(self):
        # 2024-01-13 Sat and 2024-01-14 Sun both -> Monday 2024-01-15
        self.assertEqual(late_fee("2024-01-13", "2024-01-20", 100), 0)
        self.assertEqual(late_fee("2024-01-13", "2024-01-21", 100), 100)
        self.assertEqual(late_fee("2024-01-14", "2024-01-20", 100), 0)
        self.assertEqual(late_fee("2024-01-14", "2024-01-21", 100), 100)
        self.assertEqual(late_fee("2024-01-14", "2024-01-22", 100), 200)

    def test_friday_not_moved(self):
        self.assertEqual(late_fee("2024-01-12", "2024-01-18", 100), 100)

    def test_cap_at_30(self):
        self.assertEqual(late_fee("2024-01-15", "2024-02-19", 100), 3000)  # 35 days late -> 30 chargeable
        self.assertEqual(late_fee("2024-01-15", "2024-02-20", 100), 3000)  # 36 -> 31 -> capped
        self.assertEqual(late_fee("2024-01-15", "2025-01-15", 7), 210)
        self.assertEqual(late_fee("2024-01-15", "2024-02-19", 100), 3000)
        self.assertEqual(late_fee("2024-01-15", "2024-02-18", 100), 2900)  # 34 days late

    def test_leap_day_counts(self):
        self.assertEqual(late_fee("2024-02-27", "2024-03-10", 10), 70)  # 12 days late -> 7
        self.assertEqual(late_fee("2023-02-27", "2023-03-10", 10), 60)  # 11 days late -> 6
        self.assertEqual(late_fee("2024-02-29", "2024-03-06", 10), 10)  # Thu, +6
        self.assertEqual(late_fee("2024-02-29", "2024-03-05", 10), 0)

    def test_year_boundary(self):
        self.assertEqual(late_fee("2023-12-29", "2024-01-05", 50), 100)  # Fri, +7 -> 2

    def test_zero_rate(self):
        self.assertEqual(late_fee("2024-01-15", "2024-03-15", 0), 0)

    def test_bad_date_strings(self):
        for bad in ["20240115", "2024-1-5", "2024-02-30", "2023-02-29", " 2024-01-15", "2024-01-15 ",
                    "2024-W03-1", "2024-13-01", "", "01/15/2024", "2024-01-15T00:00", "２０２４-01-15"]:
            with self.assertRaises(ValueError, msg=bad):
                late_fee(bad, "2024-02-01", 1)
            with self.assertRaises(ValueError, msg=bad):
                late_fee("2024-01-01", bad, 1)

    def test_type_errors(self):
        with self.assertRaises(TypeError):
            late_fee(None, "2024-01-01", 1)
        with self.assertRaises(TypeError):
            late_fee("2024-01-01", 20240101, 1)

    def test_bad_rate(self):
        for bad in (-1, True, False):
            with self.assertRaises(ValueError):
                late_fee("2024-01-15", "2024-02-01", bad)


if __name__ == "__main__":
    unittest.main()
