import unittest

from stats import median, summarize


class StatsTests(unittest.TestCase):
    def test_even_median(self):
        self.assertEqual(median([1, 2, 3, 4]), 2.5)

    def test_summary(self):
        self.assertEqual(summarize([1, 2, 3, 4])["median"], 2.5)


if __name__ == "__main__":
    unittest.main()
