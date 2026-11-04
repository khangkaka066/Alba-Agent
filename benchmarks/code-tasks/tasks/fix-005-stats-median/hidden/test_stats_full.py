import unittest

from stats import mean, median, summarize


class StatsFullTests(unittest.TestCase):
    def test_even_medians(self):
        self.assertEqual(median([1, 2, 3, 4]), 2.5)
        self.assertEqual(median([1, 2]), 1.5)
        self.assertEqual(median([7, 8]), 7.5)

    def test_even_unsorted(self):
        self.assertEqual(median([9, 1, 4, 2]), 3.0)

    def test_odd(self):
        self.assertEqual(median([5, 1, 3]), 3)
        self.assertEqual(median([42]), 42)

    def test_floats(self):
        self.assertAlmostEqual(median([0.5, 0.25, 1.0, 2.0]), 0.75)

    def test_negative_values(self):
        self.assertEqual(median([-3, -2]), -2.5)

    def test_input_not_modified(self):
        data = [3, 1, 2, 4]
        median(data)
        self.assertEqual(data, [3, 1, 2, 4])

    def test_empty(self):
        with self.assertRaises(ValueError):
            median([])
        with self.assertRaises(ValueError):
            mean([])

    def test_mean(self):
        self.assertEqual(mean([1, 2]), 1.5)
        self.assertEqual(mean([2, 4, 6]), 4.0)

    def test_summary(self):
        self.assertEqual(
            summarize([4, 1, 2, 3]),
            {"mean": 2.5, "median": 2.5, "min": 1, "max": 4},
        )


if __name__ == "__main__":
    unittest.main()
