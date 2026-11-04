import unittest

from cal.arith import add_days
from cal.business import business_days_between
from cal.dates import days_in_month, parse_date
from cal.format import human


class CalTests(unittest.TestCase):
    def test_century_years(self):
        self.assertEqual(days_in_month(1900, 2), 28)
        self.assertEqual(days_in_month(2000, 2), 29)

    def test_parse_is_strict(self):
        self.assertEqual(parse_date("2024-02-29"), (2024, 2, 29))
        with self.assertRaises(ValueError):
            parse_date("2024-2-5")

    def test_add_negative_days(self):
        self.assertEqual(add_days((2024, 3, 1), -1), (2024, 2, 29))

    def test_business_days_exclude_the_end(self):
        self.assertEqual(business_days_between((2024, 2, 26), (2024, 3, 1)), 4)

    def test_human(self):
        self.assertEqual(human((2024, 3, 5)), "Tue 5 Mar 2024")


if __name__ == "__main__":
    unittest.main()
