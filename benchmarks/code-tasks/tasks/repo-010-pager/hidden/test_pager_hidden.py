import base64
import json
import unittest

from pager.cursor import decode_cursor, encode_cursor
from pager.filters import apply_filters
from pager.paginate import paginate
from pager.sort import sort_items


def raw_cursor(payload):
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


class CursorTests(unittest.TestCase):
    def test_roundtrip_and_format(self):
        for offset in (0, 1, 7, 100, 12345):
            self.assertEqual(decode_cursor(encode_cursor(offset)), offset)
        self.assertEqual(encode_cursor(0), raw_cursor({"o": 0}))
        self.assertNotIn("=", encode_cursor(5))

    def test_invalid_cursors(self):
        bad = ["", "!!!", "not-a-cursor", raw_cursor([1]), raw_cursor({"x": 1}), raw_cursor({"o": 1, "x": 2}),
               raw_cursor({"o": -1}), raw_cursor({"o": "3"}), raw_cursor({"o": 1.5}), raw_cursor({"o": True}),
               raw_cursor({"o": None}), raw_cursor("text"), base64.urlsafe_b64encode(b"{bad json").decode()]
        for text in bad:
            with self.assertRaises(ValueError, msg=text):
                decode_cursor(text)


class PaginateTests(unittest.TestCase):
    items = list(range(10))

    def test_walks_the_whole_list(self):
        seen, cursor, pages = [], None, 0
        while True:
            page = paginate(self.items, 4, cursor)
            seen.extend(page["items"])
            pages += 1
            self.assertEqual(page["total"], 10)
            cursor = page["next"]
            if cursor is None:
                break
        self.assertEqual((seen, pages), (self.items, 3))

    def test_exact_multiple_ends_cleanly(self):
        first = paginate(self.items, 5)
        self.assertEqual(first["items"], [0, 1, 2, 3, 4])
        last = paginate(self.items, 5, first["next"])
        self.assertEqual(last, {"items": [5, 6, 7, 8, 9], "next": None, "total": 10})

    def test_one_page_holds_everything(self):
        self.assertEqual(paginate(self.items, 10), {"items": self.items, "next": None, "total": 10})
        self.assertEqual(paginate(self.items, 100), {"items": self.items, "next": None, "total": 10})

    def test_empty_list(self):
        self.assertEqual(paginate([], 5), {"items": [], "next": None, "total": 0})

    def test_offset_equal_to_length_is_an_empty_page(self):
        self.assertEqual(paginate(self.items, 3, encode_cursor(10)), {"items": [], "next": None, "total": 10})

    def test_offset_beyond_the_end(self):
        with self.assertRaises(ValueError):
            paginate(self.items, 3, encode_cursor(11))

    def test_limit_validation(self):
        for bad in (0, -1, 101, 2.0, "5", True, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                paginate(self.items, bad)
        self.assertEqual(len(paginate(list(range(200)), 100)["items"]), 100)
        self.assertEqual(len(paginate(self.items, 1)["items"]), 1)

    def test_invalid_cursor_text(self):
        with self.assertRaises(ValueError):
            paginate(self.items, 3, "garbage!!")

    def test_the_input_list_is_not_exposed(self):
        page = paginate(self.items, 3)
        page["items"].append("x")
        self.assertEqual(self.items, list(range(10)))


class FilterTests(unittest.TestCase):
    rows = [{"id": 1, "kind": "a", "tag": "x"}, {"id": 2, "kind": "b"}, {"id": 3, "kind": "a", "tag": None}, {"id": 4, "kind": "c", "tag": "y"}]

    def test_equality_and_conjunction(self):
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"kind": "a"})], [1, 3])
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"kind": "a", "tag": "x"})], [1])

    def test_collections_mean_membership(self):
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"kind": ["a", "c"]})], [1, 3, 4])
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"kind": ("b",)})], [2])
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"kind": {"c", "z"}})], [4])
        self.assertEqual(apply_filters(self.rows, {"kind": []}), [])

    def test_a_missing_key_never_matches(self):
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"tag": None})], [3])
        self.assertEqual([r["id"] for r in apply_filters(self.rows, {"tag": [None, "y"]})], [3, 4])
        self.assertEqual(apply_filters(self.rows, {"nope": None}), [])

    def test_no_filters_returns_a_copy(self):
        result = apply_filters(self.rows, {})
        self.assertEqual(result, self.rows)
        self.assertIsNot(result, self.rows)


class SortTests(unittest.TestCase):
    def test_ascending_and_descending(self):
        rows = [{"n": 2}, {"n": 3}, {"n": 1}]
        self.assertEqual([r["n"] for r in sort_items(rows, "n")], [1, 2, 3])
        self.assertEqual([r["n"] for r in sort_items(rows, "n", desc=True)], [3, 2, 1])

    def test_stable_in_both_directions(self):
        rows = [{"n": 1, "id": "a"}, {"n": 2, "id": "b"}, {"n": 1, "id": "c"}, {"n": 2, "id": "d"}]
        self.assertEqual([r["id"] for r in sort_items(rows, "n")], ["a", "c", "b", "d"])
        self.assertEqual([r["id"] for r in sort_items(rows, "n", desc=True)], ["b", "d", "a", "c"])

    def test_missing_and_none_go_last_in_original_order(self):
        rows = [{"id": 1}, {"id": 2, "n": 5}, {"id": 3, "n": None}, {"id": 4, "n": 1}, {"id": 5}]
        self.assertEqual([r["id"] for r in sort_items(rows, "n")], [4, 2, 1, 3, 5])
        self.assertEqual([r["id"] for r in sort_items(rows, "n", desc=True)], [2, 4, 1, 3, 5])

    def test_strings_and_new_list(self):
        rows = [{"s": "pear"}, {"s": "apple"}, {"s": "fig"}]
        result = sort_items(rows, "s")
        self.assertEqual([r["s"] for r in result], ["apple", "fig", "pear"])
        self.assertEqual([r["s"] for r in rows], ["pear", "apple", "fig"])

    def test_empty(self):
        self.assertEqual(sort_items([], "n"), [])
        self.assertEqual(sort_items([{}, {}], "n", desc=True), [{}, {}])


if __name__ == "__main__":
    unittest.main()
