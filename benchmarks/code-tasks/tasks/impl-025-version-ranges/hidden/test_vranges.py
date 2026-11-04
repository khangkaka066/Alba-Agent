import unittest

from vranges import max_satisfying, parse_version, satisfies


class ParseTests(unittest.TestCase):
    def test_parse_ok(self):
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("0.0.0"), (0, 0, 0))
        self.assertEqual(parse_version("1.02.003"), (1, 2, 3))
        self.assertEqual(parse_version("10.20.30"), (10, 20, 30))

    def test_parse_bad(self):
        for bad in ["", "1", "1.2", "1.2.3.4", "v1.2.3", "1.2.x", "1.2.3-beta", " 1.2.3", "1.2.3 ", "1..3", "-1.2.3", "1.2.+3"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_version(bad)


class SatisfiesTests(unittest.TestCase):
    def test_comparison_operators(self):
        self.assertTrue(satisfies("1.2.3", ">=1.2.3"))
        self.assertFalse(satisfies("1.2.2", ">=1.2.3"))
        self.assertTrue(satisfies("1.2.3", "<=1.2.3"))
        self.assertFalse(satisfies("1.2.4", "<=1.2.3"))
        self.assertTrue(satisfies("2.0.0", ">1.9.9"))
        self.assertFalse(satisfies("1.9.9", ">1.9.9"))
        self.assertTrue(satisfies("1.9.8", "<1.9.9"))
        self.assertFalse(satisfies("1.9.9", "<1.9.9"))
        self.assertTrue(satisfies("1.0.0", "!=1.0.1"))
        self.assertFalse(satisfies("1.0.1", "!=1.0.1"))

    def test_equality_forms(self):
        for spec in ("1.2.3", "=1.2.3", "==1.2.3", "== 1.2.3", " 1.2.3 "):
            self.assertTrue(satisfies("1.2.3", spec), spec)
            self.assertFalse(satisfies("1.2.4", spec), spec)
        self.assertTrue(satisfies("1.02.3", "1.2.3"))

    def test_numeric_not_lexicographic(self):
        self.assertTrue(satisfies("1.10.0", ">1.9.0"))
        self.assertTrue(satisfies("10.0.0", ">=9.9.9"))
        self.assertFalse(satisfies("1.9.0", ">=1.10.0"))

    def test_wildcard(self):
        self.assertTrue(satisfies("0.0.1", "*"))
        self.assertTrue(satisfies("99.0.0", " * "))
        self.assertFalse(satisfies("1.0.0", "*, <1.0.0"))

    def test_and_clauses(self):
        spec = ">=1.2.0, <2.0.0"
        self.assertTrue(satisfies("1.2.0", spec))
        self.assertTrue(satisfies("1.99.99", spec))
        self.assertFalse(satisfies("2.0.0", spec))
        self.assertFalse(satisfies("1.1.9", spec))
        self.assertFalse(satisfies("1.5.0", ">=1.2.0,<2.0.0,!=1.5.0"))
        self.assertTrue(satisfies("1.5.1", ">=1.2.0,<2.0.0,!=1.5.0"))

    def test_or_alternatives(self):
        spec = "<1.0.0 || >=2.0.0,<2.5.0 || 3.1.4"
        for good in ["0.9.9", "2.0.0", "2.4.9", "3.1.4"]:
            self.assertTrue(satisfies(good, spec), good)
        for bad in ["1.0.0", "1.9.9", "2.5.0", "3.1.5"]:
            self.assertFalse(satisfies(bad, spec), bad)

    def test_tilde(self):
        self.assertTrue(satisfies("1.2.3", "~1.2.3"))
        self.assertTrue(satisfies("1.2.99", "~1.2.3"))
        self.assertFalse(satisfies("1.2.2", "~1.2.3"))
        self.assertFalse(satisfies("1.3.0", "~1.2.3"))
        self.assertTrue(satisfies("0.4.9", "~ 0.4.0"))
        self.assertFalse(satisfies("0.5.0", "~0.4.0"))

    def test_caret(self):
        self.assertTrue(satisfies("1.2.3", "^1.2.3"))
        self.assertTrue(satisfies("1.99.0", "^1.2.3"))
        self.assertFalse(satisfies("2.0.0", "^1.2.3"))
        self.assertFalse(satisfies("1.2.2", "^1.2.3"))
        self.assertTrue(satisfies("0.2.9", "^0.2.3"))
        self.assertFalse(satisfies("0.3.0", "^0.2.3"))
        self.assertFalse(satisfies("0.2.2", "^0.2.3"))
        self.assertTrue(satisfies("0.0.3", "^0.0.3"))
        self.assertFalse(satisfies("0.0.4", "^0.0.3"))
        self.assertFalse(satisfies("0.0.2", "^0.0.3"))
        self.assertTrue(satisfies("0.9.9", "^0.0.0 || ^0.9.0"))
        self.assertTrue(satisfies("0.0.0", "^0.0.0"))
        self.assertFalse(satisfies("0.0.1", "^0.0.0"))

    def test_combined_with_caret_and_or(self):
        spec = "^1.4.0 || ^2.1.0, !=2.3.0"
        self.assertTrue(satisfies("1.9.0", spec))
        self.assertFalse(satisfies("1.3.9", spec))
        self.assertTrue(satisfies("2.2.0", spec))
        self.assertFalse(satisfies("2.3.0", spec))
        self.assertFalse(satisfies("3.0.0", spec))

    def test_invalid_specs(self):
        for spec in ["", "  ", ">=1.0.0,", ",>=1.0.0", "||", "1.0.0 ||", ">=", "^", "~1.2", ">=1.2", "~>1.2.3", "=>1.0.0", "1.x.0", "foo", ">== 1.0.0", ">=1.0.0 <2.0.0", "**"]:
            with self.assertRaises(ValueError, msg=repr(spec)):
                satisfies("1.0.0", spec)

    def test_whole_spec_validated_first(self):
        with self.assertRaises(ValueError):
            satisfies("1.0.0", "1.0.0 || nonsense")
        with self.assertRaises(ValueError):
            satisfies("1.0.0", "*||")

    def test_bad_version_argument(self):
        with self.assertRaises(ValueError):
            satisfies("1.0", "*")


class MaxSatisfyingTests(unittest.TestCase):
    VERSIONS = ["1.0.0", "1.9.0", "1.10.0", "2.0.0", "2.1.5", "0.9.9"]

    def test_picks_highest_numerically(self):
        self.assertEqual(max_satisfying(self.VERSIONS, "^1.0.0"), "1.10.0")
        self.assertEqual(max_satisfying(self.VERSIONS, "<2.0.0"), "1.10.0")
        self.assertEqual(max_satisfying(self.VERSIONS, "*"), "2.1.5")
        self.assertEqual(max_satisfying(self.VERSIONS, "~1.9.0 || 0.9.9"), "1.9.0")

    def test_none_when_nothing_matches(self):
        self.assertIsNone(max_satisfying(self.VERSIONS, ">=3.0.0"))
        self.assertIsNone(max_satisfying([], "*"))

    def test_returns_original_text_first_wins_on_tie(self):
        self.assertEqual(max_satisfying(["1.02.3", "1.2.3"], "*"), "1.02.3")
        self.assertEqual(max_satisfying(["1.2.3", "1.02.3"], "*"), "1.2.3")

    def test_accepts_any_iterable(self):
        self.assertEqual(max_satisfying(iter(["1.0.0", "1.1.0"]), "^1.0.0"), "1.1.0")
        self.assertEqual(max_satisfying(("0.1.0",), "*"), "0.1.0")

    def test_errors(self):
        with self.assertRaises(ValueError):
            max_satisfying(["1.0.0", "bad"], "*")
        with self.assertRaises(ValueError):
            max_satisfying([], "")
        with self.assertRaises(ValueError):
            max_satisfying(["1.0.0"], ">=oops")


if __name__ == "__main__":
    unittest.main()
