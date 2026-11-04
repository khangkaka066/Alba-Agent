import unittest

from intervals import covered_points, merge_intervals


class MergeTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(merge_intervals([]), [])

    def test_overlapping_and_unsorted(self):
        self.assertEqual(merge_intervals([(8, 10), (1, 3), (2, 6), (15, 18)]), [(1, 6), (8, 10), (15, 18)])

    def test_shared_endpoint_merges(self):
        self.assertEqual(merge_intervals([(1, 3), (3, 5)]), [(1, 5)])
        self.assertEqual(merge_intervals([(5, 9), (1, 5)]), [(1, 9)])

    def test_adjacent_without_shared_point_not_merged(self):
        self.assertEqual(merge_intervals([(1, 2), (3, 4)]), [(1, 2), (3, 4)])

    def test_contained_and_duplicates(self):
        self.assertEqual(merge_intervals([(1, 10), (2, 3), (4, 4), (1, 10)]), [(1, 10)])
        self.assertEqual(merge_intervals([(2, 2), (2, 2)]), [(2, 2)])

    def test_negative_numbers(self):
        self.assertEqual(merge_intervals([(-5, -1), (-3, 2), (4, 4)]), [(-5, 2), (4, 4)])

    def test_input_not_modified_and_returns_tuples(self):
        data = [(5, 6), (1, 2), (2, 3)]
        out = merge_intervals(data)
        self.assertEqual(data, [(5, 6), (1, 2), (2, 3)])
        self.assertEqual(out, [(1, 3), (5, 6)])
        self.assertTrue(all(type(item) is tuple for item in out))

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            merge_intervals([(3, 1)])
        with self.assertRaises(ValueError):
            merge_intervals([(1, 10), (5, 4)])


class CoveredPointsTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(covered_points([]), 0)
        self.assertEqual(covered_points([(1, 3), (3, 5)]), 5)
        self.assertEqual(covered_points([(1, 2), (3, 4)]), 4)
        self.assertEqual(covered_points([(7, 7)]), 1)
        self.assertEqual(covered_points([(0, 9), (2, 4), (20, 29)]), 20)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            covered_points([(2, 1)])


if __name__ == "__main__":
    unittest.main()
