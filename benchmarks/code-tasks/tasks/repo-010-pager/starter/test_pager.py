import unittest

from pager.cursor import decode_cursor, encode_cursor
from pager.filters import apply_filters
from pager.paginate import paginate
from pager.sort import sort_items


class PagerTests(unittest.TestCase):
    def test_negative_cursor_is_invalid(self):
        with self.assertRaises(ValueError):
            decode_cursor(encode_cursor(-1))

    def test_last_page_has_no_next(self):
        page = paginate([1, 2, 3, 4], 2, encode_cursor(2))
        self.assertEqual(page, {"items": [3, 4], "next": None, "total": 4})

    def test_a_missing_key_never_matches(self):
        self.assertEqual(apply_filters([{"a": 1}, {"b": 2}], {"a": None}), [])

    def test_missing_values_sort_last_when_descending(self):
        items = [{"n": 1}, {}, {"n": 3}]
        self.assertEqual(sort_items(items, "n", desc=True), [{"n": 3}, {"n": 1}, {}])


if __name__ == "__main__":
    unittest.main()
