import unittest

from sizes import format_size, parse_size


class FormatTests(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1), "1 B")
        self.assertEqual(format_size(1023), "1023 B")

    def test_exact_units(self):
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(1024**2), "1.0 MB")
        self.assertEqual(format_size(1024**3), "1.0 GB")
        self.assertEqual(format_size(1024**4), "1.0 TB")
        self.assertEqual(format_size(1024**5), "1.0 PB")

    def test_one_decimal(self):
        self.assertEqual(format_size(1536), "1.5 KB")
        self.assertEqual(format_size(5 * 1024**2 + 1024**2 // 4), "5.3 MB")
        self.assertEqual(format_size(10 * 1024), "10.0 KB")

    def test_half_up_on_exact_tie(self):
        self.assertEqual(format_size(1280), "1.3 KB")   # 1.25
        self.assertEqual(format_size(1024 + 51), "1.0 KB")  # 1.0498
        self.assertEqual(format_size(1024 + 52), "1.1 KB")  # 1.0508
        self.assertEqual(format_size(1024 * 3 + 512), "3.5 KB")

    def test_rounding_promotes_unit(self):
        self.assertEqual(format_size(1048575), "1.0 MB")
        self.assertEqual(format_size(1024**3 - 1), "1.0 GB")
        self.assertEqual(format_size(1023 * 1024 + 512), "1023.5 KB")

    def test_pb_is_largest(self):
        self.assertEqual(format_size(2048 * 1024**5), "2048.0 PB")
        self.assertEqual(format_size(1024**6 - 1), "1024.0 PB")

    def test_negative(self):
        with self.assertRaises(ValueError):
            format_size(-1)


class ParseTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_size("0 B"), 0)
        self.assertEqual(parse_size("512 B"), 512)
        self.assertEqual(parse_size("1 KB"), 1024)
        self.assertEqual(parse_size("3GB"), 3 * 1024**3)

    def test_fractions_truncate(self):
        self.assertEqual(parse_size("1.5 KB"), 1536)
        self.assertEqual(parse_size("0.1 KB"), 102)
        self.assertEqual(parse_size("2.5 B"), 2)

    def test_case_and_whitespace(self):
        self.assertEqual(parse_size("  10mb "), 10 * 1024**2)
        self.assertEqual(parse_size("1 pB"), 1024**5)
        self.assertEqual(parse_size("4\tTB"), 4 * 1024**4)

    def test_invalid(self):
        for text in ["", "KB", "12", "5 XB", "5 K", "-1 KB", "1 2 KB", "1.KB", "1e3 KB", "abc", "1,5 KB", "+1 KB"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_size(text)

    def test_exact_big_value_no_float_error(self):
        self.assertEqual(parse_size("9007199254740993 B"), 9007199254740993)


if __name__ == "__main__":
    unittest.main()
