import unittest

from pager import describe_page, page_count, paginate


class PagerFullTests(unittest.TestCase):
    def setUp(self):
        self.items = list(range(1, 11))

    def test_first_and_second_page(self):
        self.assertEqual(paginate(self.items, 1, 3), [1, 2, 3])
        self.assertEqual(paginate(self.items, 2, 3), [4, 5, 6])

    def test_last_partial_page(self):
        self.assertEqual(paginate(self.items, 4, 3), [10])

    def test_exact_last_page(self):
        self.assertEqual(paginate(self.items, 2, 5), [6, 7, 8, 9, 10])

    def test_past_the_end(self):
        self.assertEqual(paginate(self.items, 5, 3), [])
        self.assertEqual(paginate([], 1, 3), [])

    def test_default_per_page(self):
        data = list(range(50))
        self.assertEqual(paginate(data, 1), data[:20])
        self.assertEqual(paginate(data, 3), data[40:])

    def test_returns_new_list(self):
        page = paginate(self.items, 1, 10)
        page.append(99)
        self.assertEqual(self.items[-1], 10)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            paginate(self.items, 0, 3)
        with self.assertRaises(ValueError):
            paginate(self.items, 1, 0)

    def test_page_count(self):
        self.assertEqual(page_count(0, 10), 0)
        self.assertEqual(page_count(10, 5), 2)
        self.assertEqual(page_count(11, 5), 3)

    def test_describe_page(self):
        self.assertEqual(describe_page(95, 2, 20), "Showing 21-40 of 95")
        self.assertEqual(describe_page(95, 5, 20), "Showing 81-95 of 95")
        self.assertEqual(describe_page(95, 6, 20), "No results")


if __name__ == "__main__":
    unittest.main()
