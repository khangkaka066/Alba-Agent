import unittest

from cal.arith import add_days
from cal.business import business_days_between, next_business_day, weekday
from cal.dates import days_in_month, is_leap, parse_date
from cal.format import human


class DatesTests(unittest.TestCase):
    def test_leap_years(self):
        for year, leap in [(2024, True), (2023, False), (1900, False), (2000, True), (2100, False), (1600, True), (4, True)]:
            self.assertEqual(is_leap(year), leap, year)

    def test_days_in_month(self):
        self.assertEqual([days_in_month(2023, m) for m in range(1, 13)], [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        self.assertEqual(days_in_month(1900, 2), 28)
        self.assertEqual(days_in_month(2000, 2), 29)
        for month in (0, 13):
            with self.assertRaises(ValueError):
                days_in_month(2024, month)

    def test_parse_valid(self):
        self.assertEqual(parse_date("2024-02-29"), (2024, 2, 29))
        self.assertEqual(parse_date("0001-01-01"), (1, 1, 1))
        self.assertEqual(parse_date("2000-02-29"), (2000, 2, 29))

    def test_parse_invalid(self):
        for text in ["2024-2-5", "2024-02-5", "24-02-05", " 2024-02-05", "2024-02-05 ", "2023-02-29", "1900-02-29",
                     "2024-13-01", "2024-00-10", "2024-04-31", "0000-01-01", "2024/02/05", "", "abcd-ef-gh", None, 20240205]:
            with self.assertRaises(ValueError, msg=repr(text)):
                parse_date(text)


class ArithTests(unittest.TestCase):
    def test_add_days(self):
        self.assertEqual(add_days((2024, 2, 28), 1), (2024, 2, 29))
        self.assertEqual(add_days((2023, 2, 28), 1), (2023, 3, 1))
        self.assertEqual(add_days((2024, 12, 31), 1), (2025, 1, 1))
        self.assertEqual(add_days((2024, 3, 1), -1), (2024, 2, 29))
        self.assertEqual(add_days((2024, 1, 1), -1), (2023, 12, 31))
        self.assertEqual(add_days((2024, 1, 1), 0), (2024, 1, 1))
        self.assertEqual(add_days((2024, 1, 1), 366), (2025, 1, 1))
        self.assertEqual(add_days((2024, 1, 1), -366), (2022, 12, 31))
        self.assertEqual(add_days((2000, 1, 1), 10000), (2027, 5, 19))

    def test_range(self):
        with self.assertRaises(ValueError):
            add_days((1, 1, 1), -1)
        with self.assertRaises(ValueError):
            add_days((9999, 12, 31), 1)
        self.assertEqual(add_days((9999, 12, 30), 1), (9999, 12, 31))


class BusinessTests(unittest.TestCase):
    def test_weekday(self):
        self.assertEqual(weekday((2024, 2, 29)), 3)
        self.assertEqual(weekday((2024, 3, 3)), 6)

    def test_between_is_half_open(self):
        self.assertEqual(business_days_between((2024, 2, 26), (2024, 3, 1)), 4)   # Mon..Thu
        self.assertEqual(business_days_between((2024, 2, 26), (2024, 3, 4)), 5)   # Mon..Fri, end is a Monday
        self.assertEqual(business_days_between((2024, 3, 2), (2024, 3, 4)), 0)    # Sat, Sun
        self.assertEqual(business_days_between((2024, 3, 1), (2024, 3, 2)), 1)    # Fri only
        self.assertEqual(business_days_between((2024, 3, 4), (2024, 3, 4)), 0)
        self.assertEqual(business_days_between((2024, 3, 8), (2024, 3, 4)), 0)
        self.assertEqual(business_days_between((2024, 1, 1), (2024, 1, 15)), 10)

    def test_next_business_day(self):
        self.assertEqual(next_business_day((2024, 2, 29)), (2024, 3, 1))
        self.assertEqual(next_business_day((2024, 3, 1)), (2024, 3, 4))
        self.assertEqual(next_business_day((2024, 3, 2)), (2024, 3, 4))


class FormatTests(unittest.TestCase):
    def test_human(self):
        self.assertEqual(human((2024, 2, 29)), "Thu 29 Feb 2024")
        self.assertEqual(human((2024, 3, 5)), "Tue 5 Mar 2024")
        self.assertEqual(human((2023, 12, 31)), "Sun 31 Dec 2023")
        self.assertEqual(human((2024, 1, 1)), "Mon 1 Jan 2024")


if __name__ == "__main__":
    unittest.main()
