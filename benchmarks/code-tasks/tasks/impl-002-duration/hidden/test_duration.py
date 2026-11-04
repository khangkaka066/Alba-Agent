import unittest

from duration import format_duration, parse_duration


class ParseTests(unittest.TestCase):
    def test_single_units(self):
        self.assertEqual(parse_duration("45s"), 45)
        self.assertEqual(parse_duration("2m"), 120)
        self.assertEqual(parse_duration("3h"), 10800)
        self.assertEqual(parse_duration("1d"), 86400)

    def test_combined(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("2d4h5s"), 2 * 86400 + 4 * 3600 + 5)

    def test_whitespace(self):
        self.assertEqual(parse_duration("  1h   30m 15s "), 5415)
        self.assertEqual(parse_duration("1d 1s"), 86401)

    def test_large_and_zero_values(self):
        self.assertEqual(parse_duration("90m"), 5400)
        self.assertEqual(parse_duration("0s"), 0)
        self.assertEqual(parse_duration("007s"), 7)

    def test_invalid_raise_value_error(self):
        bad = ["", "   ", "10", "h", "5x", "1h 1h", "30m 1h", "1.5h", "-5s", "+5s",
               "1h and 5m", "1 h", "5S", "1h,2m", "m5"]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_duration(text)


class FormatTests(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_duration(0), "0s")

    def test_basic(self):
        self.assertEqual(format_duration(59), "59s")
        self.assertEqual(format_duration(60), "1m")
        self.assertEqual(format_duration(3725), "1h 2m 5s")

    def test_zero_components_dropped(self):
        self.assertEqual(format_duration(3600), "1h")
        self.assertEqual(format_duration(86400 + 5), "1d 5s")
        self.assertEqual(format_duration(90000), "1d 1h")

    def test_days_do_not_roll_up(self):
        self.assertEqual(format_duration(100000000), "1157d 9h 46m 40s")

    def test_negative(self):
        with self.assertRaises(ValueError):
            format_duration(-1)

    def test_round_trip(self):
        for n in (0, 1, 59, 60, 61, 3599, 3600, 86399, 86400, 123456, 9999999):
            with self.subTest(n=n):
                self.assertEqual(parse_duration(format_duration(n)), n)
        self.assertEqual(format_duration(parse_duration("90m")), "1h 30m")


if __name__ == "__main__":
    unittest.main()
