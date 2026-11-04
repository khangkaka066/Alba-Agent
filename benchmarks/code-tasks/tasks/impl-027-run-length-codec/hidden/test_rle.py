import unittest

from rle import decode, encode, runs


class RunsTests(unittest.TestCase):
    def test_runs(self):
        self.assertEqual(runs(""), [])
        self.assertEqual(runs("aab"), [("a", 2), ("b", 1)])
        self.assertEqual(runs("abab"), [("a", 1), ("b", 1), ("a", 1), ("b", 1)])
        self.assertEqual(runs("zzzzz"), [("z", 5)])
        self.assertEqual(runs("aAa"), [("a", 1), ("A", 1), ("a", 1)])


class EncodeTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(encode(""), "")
        self.assertEqual(encode("aaabcc"), "3a1b2c")
        self.assertEqual(encode("a"), "1a")
        self.assertEqual(encode("abc"), "1a1b1c")

    def test_long_runs(self):
        self.assertEqual(encode("a" * 1000), "1000a")
        self.assertEqual(encode("x" * 12 + "y"), "12x1y")

    def test_digits_and_backslash_are_escaped(self):
        self.assertEqual(encode("111"), "3\\1")
        self.assertEqual(encode("a1"), "1a1\\1")
        self.assertEqual(encode("\\"), "1\\\\")
        self.assertEqual(encode("\\\\x"), "2\\\\1x")
        self.assertEqual(encode("0" * 10), "10\\0")
        self.assertEqual(encode("9"), "1\\9")

    def test_other_characters_not_escaped(self):
        self.assertEqual(encode("  \n\n\n"), "2 3\n")
        self.assertEqual(encode("éé€"), "2é1€")
        self.assertEqual(encode("-.-"), "1-1.1-")


class DecodeTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(decode(""), "")
        self.assertEqual(decode("3a1b2c"), "aaabcc")
        self.assertEqual(decode("1000a"), "a" * 1000)
        self.assertEqual(decode("12x1y"), "x" * 12 + "y")

    def test_escapes(self):
        self.assertEqual(decode("3\\1"), "111")
        self.assertEqual(decode("1a1\\1"), "a1")
        self.assertEqual(decode("1\\\\"), "\\")
        self.assertEqual(decode("2\\\\1x"), "\\\\x")
        self.assertEqual(decode("10\\0"), "0" * 10)

    def test_non_canonical_input_accepted(self):
        self.assertEqual(decode("1a1a"), "aa")
        self.assertEqual(decode("2a3a"), "aaaaa")

    def test_malformed(self):
        for bad in ["a3b", "a", "\\1", "3", "3a2", "01a", "0a", "00a", "1\\a", "1\\", "3\\", "5\\x", "1a\\1", "12", "2a-"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                decode(bad)

    def test_max_length(self):
        self.assertEqual(decode("3a2b", max_length=5), "aaabb")
        self.assertEqual(decode("", max_length=0), "")
        with self.assertRaises(ValueError):
            decode("3a2b", max_length=4)
        with self.assertRaises(ValueError):
            decode("1a1a1a", max_length=2)
        with self.assertRaises(ValueError):
            decode("1a", max_length=0)

    def test_max_length_rejects_before_allocating(self):
        with self.assertRaises(ValueError):
            decode("999999999999999999a", max_length=1000)
        with self.assertRaises(ValueError):
            decode("1a999999999999999999\\1", max_length=10)

    def test_malformed_still_raises_with_max_length(self):
        with self.assertRaises(ValueError):
            decode("a3", max_length=100)
        with self.assertRaises(ValueError):
            decode("2a3", max_length=100)


class RoundTripTests(unittest.TestCase):
    def test_round_trip(self):
        samples = [
            "", "a", "aaaa", "abc", "1", "111222", "\\", "\\\\11\\", "a1b2c3", "0" * 25,
            "hello  world\n\n", "日本語語語", "12345678901234567890", "x" * 500 + "9" * 11 + "\\" * 3,
        ]
        for s in samples:
            self.assertEqual(decode(encode(s)), s, repr(s))
            self.assertEqual(decode(encode(s), max_length=len(s)), s, repr(s))


if __name__ == "__main__":
    unittest.main()
