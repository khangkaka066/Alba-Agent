import unittest

from pager import page_bounds, page_window


class PageWindowTests(unittest.TestCase):
    def test_middle(self):
        self.assertEqual(page_window(5, 10), [1, "...", 4, 5, 6, "...", 10])

    def test_near_start_and_end(self):
        self.assertEqual(page_window(1, 10), [1, 2, "...", 10])
        self.assertEqual(page_window(2, 10), [1, 2, 3, "...", 10])
        self.assertEqual(page_window(10, 10), [1, "...", 9, 10])
        self.assertEqual(page_window(9, 10), [1, "...", 8, 9, 10])

    def test_single_missing_page_is_shown_instead_of_marker(self):
        self.assertEqual(page_window(4, 7), [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(page_window(4, 10), [1, 2, 3, 4, 5, "...", 10])
        self.assertEqual(page_window(7, 10), [1, "...", 6, 7, 8, 9, 10])

    def test_two_missing_pages_get_a_marker(self):
        self.assertEqual(page_window(5, 8), [1, "...", 4, 5, 6, 7, 8])
        self.assertEqual(page_window(6, 12), [1, "...", 5, 6, 7, "...", 12])

    def test_tiny_totals(self):
        self.assertEqual(page_window(1, 1), [1])
        self.assertEqual(page_window(1, 2), [1, 2])
        self.assertEqual(page_window(2, 3), [1, 2, 3])

    def test_siblings_and_edges(self):
        self.assertEqual(page_window(8, 20, siblings=0, edges=2), [1, 2, "...", 8, "...", 19, 20])
        self.assertEqual(page_window(10, 20, siblings=2), [1, "...", 8, 9, 10, 11, 12, "...", 20])
        self.assertEqual(page_window(5, 9, siblings=3), [1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(page_window(10, 30, siblings=1, edges=3), [1, 2, 3, "...", 9, 10, 11, "...", 28, 29, 30])

    def test_edges_zero(self):
        self.assertEqual(page_window(10, 20, edges=0), [9, 10, 11])
        self.assertEqual(page_window(1, 20, edges=0), [1, 2])
        self.assertEqual(page_window(1, 5, siblings=0, edges=0), [1])

    def test_edges_larger_than_total(self):
        self.assertEqual(page_window(2, 4, edges=10), [1, 2, 3, 4])

    def test_output_types(self):
        out = page_window(50, 100)
        self.assertEqual(out, [1, "...", 49, 50, 51, "...", 100])
        self.assertTrue(all(isinstance(x, int) or x == "..." for x in out))

    def test_validation(self):
        for args in [(0, 5), (6, 5), (1, 0), (1, -3), (-1, 5)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    page_window(*args)
        with self.assertRaises(ValueError):
            page_window(1, 5, siblings=-1)
        with self.assertRaises(ValueError):
            page_window(1, 5, edges=-1)


class PageBoundsTests(unittest.TestCase):
    def test_pages(self):
        self.assertEqual(page_bounds(1, 10, 25), (0, 10))
        self.assertEqual(page_bounds(2, 10, 25), (10, 20))
        self.assertEqual(page_bounds(3, 10, 25), (20, 25))
        self.assertEqual(page_bounds(1, 10, 10), (0, 10))
        self.assertEqual(page_bounds(2, 10, 10), (10, 10))

    def test_beyond_end_is_empty_slice_at_total(self):
        self.assertEqual(page_bounds(9, 10, 25), (25, 25))
        self.assertEqual(page_bounds(1, 10, 0), (0, 0))
        self.assertEqual(page_bounds(5, 3, 0), (0, 0))

    def test_slicing_matches(self):
        items = list(range(23))
        pages = []
        for page in range(1, 5):
            s, e = page_bounds(page, 6, len(items))
            pages.append(items[s:e])
        self.assertEqual(sum(pages, []), items)
        self.assertEqual(pages[-1], [18, 19, 20, 21, 22])

    def test_validation(self):
        for args in [(0, 10, 5), (1, 0, 5), (1, 10, -1), (-2, 10, 5)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    page_bounds(*args)


if __name__ == "__main__":
    unittest.main()
