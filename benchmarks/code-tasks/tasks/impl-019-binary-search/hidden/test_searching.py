import unittest

from searching import count_in_range, first_true, lower_bound, nearest, upper_bound

DATA = [1, 3, 3, 3, 7, 9, 9, 20]


class SearchingTests(unittest.TestCase):
    def test_lower_bound(self):
        self.assertEqual(lower_bound(DATA, 3), 1)
        self.assertEqual(lower_bound(DATA, 0), 0)
        self.assertEqual(lower_bound(DATA, 4), 4)
        self.assertEqual(lower_bound(DATA, 20), 7)
        self.assertEqual(lower_bound(DATA, 21), 8)
        self.assertEqual(lower_bound([], 5), 0)

    def test_upper_bound(self):
        self.assertEqual(upper_bound(DATA, 3), 4)
        self.assertEqual(upper_bound(DATA, 0), 0)
        self.assertEqual(upper_bound(DATA, 9), 7)
        self.assertEqual(upper_bound(DATA, 20), 8)
        self.assertEqual(upper_bound([], 5), 0)

    def test_bounds_match_brute_force(self):
        data = [0, 0, 1, 2, 2, 2, 5, 8, 8]
        for x in range(-1, 11):
            self.assertEqual(lower_bound(data, x), sum(1 for v in data if v < x), x)
            self.assertEqual(upper_bound(data, x), sum(1 for v in data if v <= x), x)

    def test_count_in_range(self):
        self.assertEqual(count_in_range(DATA, 3, 9), 6)
        self.assertEqual(count_in_range(DATA, 4, 6), 0)
        self.assertEqual(count_in_range(DATA, 0, 100), 8)
        self.assertEqual(count_in_range(DATA, 9, 9), 2)
        self.assertEqual(count_in_range(DATA, 10, 5), 0)
        self.assertEqual(count_in_range([], 0, 1), 0)
        self.assertEqual(count_in_range([1.5, 2.5, 3.5], 1.5, 3.4), 2)

    def test_nearest(self):
        self.assertEqual(nearest(DATA, 8), 7)  # 7 and 9 are equally close, smaller wins
        self.assertEqual(nearest(DATA, 8.5), 9)
        self.assertEqual(nearest(DATA, -100), 1)
        self.assertEqual(nearest(DATA, 1000), 20)
        self.assertEqual(nearest(DATA, 3), 3)
        self.assertEqual(nearest([5], 100), 5)
        self.assertEqual(nearest([2, 4], 3), 2)
        self.assertEqual(nearest([10, 20, 30], 26), 30)

    def test_nearest_empty(self):
        with self.assertRaises(ValueError):
            nearest([], 1)

    def test_first_true(self):
        self.assertEqual(first_true(lambda n: n >= 37, 0, 100), 37)
        self.assertEqual(first_true(lambda n: n >= 0, 0, 100), 0)
        self.assertEqual(first_true(lambda n: False, 0, 100), 100)
        self.assertEqual(first_true(lambda n: n >= 5, 3, 4), 4)
        self.assertEqual(first_true(lambda n: n * n >= 50, -20, 20), 8)
        self.assertEqual(first_true(lambda n: n >= -3, -10, 10), -3)

    def test_first_true_empty_range_does_not_call_pred(self):
        def boom(n):
            raise AssertionError("pred must not be called")

        self.assertEqual(first_true(boom, 5, 5), 5)
        self.assertEqual(first_true(boom, 9, 2), 2)

    def test_first_true_is_logarithmic(self):
        calls = []

        def pred(n):
            calls.append(n)
            return n >= 123_456

        self.assertEqual(first_true(pred, 0, 5_000_000), 123_456)
        self.assertLessEqual(len(calls), 30)

    def test_does_not_mutate(self):
        data = [1, 2, 3]
        lower_bound(data, 2)
        nearest(data, 2)
        self.assertEqual(data, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
