import unittest

from semver import bump_version, compare_versions, sort_versions


class CompareTests(unittest.TestCase):
    def test_core_numeric(self):
        self.assertEqual(compare_versions("1.2.3", "1.2.3"), 0)
        self.assertEqual(compare_versions("1.2.3", "1.2.4"), -1)
        self.assertEqual(compare_versions("1.10.0", "1.9.0"), 1)
        self.assertEqual(compare_versions("2.0.0", "10.0.0"), -1)

    def test_prerelease_lower_than_release(self):
        self.assertEqual(compare_versions("1.0.0-rc.1", "1.0.0"), -1)
        self.assertEqual(compare_versions("1.0.0", "1.0.0-rc.1"), 1)
        self.assertEqual(compare_versions("1.0.1-alpha", "1.0.0"), 1)

    def test_prerelease_ordering_chain(self):
        chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                 "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        for lo, hi in zip(chain, chain[1:]):
            with self.subTest(lo=lo, hi=hi):
                self.assertEqual(compare_versions(lo, hi), -1)
                self.assertEqual(compare_versions(hi, lo), 1)

    def test_numeric_vs_alpha_identifiers(self):
        self.assertEqual(compare_versions("1.0.0-1", "1.0.0-a"), -1)
        self.assertEqual(compare_versions("1.0.0-2", "1.0.0-10"), -1)
        self.assertEqual(compare_versions("1.0.0-a-b", "1.0.0-a1"), -1)
        self.assertEqual(compare_versions("1.0.0-B", "1.0.0-a"), -1)  # ASCII order

    def test_build_and_v_prefix_ignored(self):
        self.assertEqual(compare_versions("1.0.0+build.5", "1.0.0"), 0)
        self.assertEqual(compare_versions("v1.0.0", "1.0.0"), 0)
        self.assertEqual(compare_versions("v1.2.3-rc.1+x", "1.2.3-rc.1+y"), 0)

    def test_invalid(self):
        bad = ["", "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.3-", "1.0.0-a..b",
               "1.0.0-01", "1.0.0+", "1.0.0 ", " 1.0.0", "V1.0.0", "vv1.0.0", "1.0.0-a_b", "a.b.c", "1.0.0+a..b"]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    compare_versions(text, "1.0.0")
                with self.assertRaises(ValueError):
                    compare_versions("1.0.0", text)

    def test_zero_prerelease_identifier_allowed(self):
        self.assertEqual(compare_versions("1.0.0-0", "1.0.0-1"), -1)
        self.assertEqual(compare_versions("1.0.0-0a", "1.0.0-0a"), 0)


class SortTests(unittest.TestCase):
    def test_sort(self):
        data = ["1.10.0", "1.2.0", "1.2.0-rc.1", "v1.0.0", "0.9.9", "1.2.0-alpha"]
        self.assertEqual(
            sort_versions(data),
            ["0.9.9", "v1.0.0", "1.2.0-alpha", "1.2.0-rc.1", "1.2.0", "1.10.0"],
        )
        self.assertEqual(data[0], "1.10.0")  # input untouched

    def test_stable_for_equal(self):
        self.assertEqual(sort_versions(["1.0.0+b", "v1.0.0", "1.0.0+a", "0.1.0"]),
                         ["0.1.0", "1.0.0+b", "v1.0.0", "1.0.0+a"])

    def test_empty_and_invalid(self):
        self.assertEqual(sort_versions([]), [])
        with self.assertRaises(ValueError):
            sort_versions(["1.0.0", "nope"])


class BumpTests(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(bump_version("1.2.3", "patch"), "1.2.4")
        self.assertEqual(bump_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump_version("1.2.3", "major"), "2.0.0")

    def test_drops_prerelease_build_and_prefix(self):
        self.assertEqual(bump_version("v1.2.3-rc.1+abc", "patch"), "1.2.4")
        self.assertEqual(bump_version("0.9.9-beta", "minor"), "0.10.0")
        self.assertEqual(bump_version("9.9.9+x", "major"), "10.0.0")

    def test_errors(self):
        with self.assertRaises(ValueError):
            bump_version("1.2.3", "build")
        with self.assertRaises(ValueError):
            bump_version("1.2.3", "PATCH")
        with self.assertRaises(ValueError):
            bump_version("1.2", "patch")


if __name__ == "__main__":
    unittest.main()
