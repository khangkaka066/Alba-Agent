import unittest

from pager import paginate


class PagerTests(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate(list(range(1, 11)), 1, 3), [1, 2, 3])

    def test_second_page(self):
        self.assertEqual(paginate(list(range(1, 11)), 2, 3), [4, 5, 6])


if __name__ == "__main__":
    unittest.main()
