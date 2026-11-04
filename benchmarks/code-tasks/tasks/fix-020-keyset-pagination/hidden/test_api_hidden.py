import unittest

from api import decode_cursor, encode_cursor, list_entries
from paging import is_after, page
from sorting import sort_items

ENTRIES = (
    [{"id": i, "score": 40, "tag": "x" if i % 2 else "y"} for i in range(1, 8)]
    + [{"id": 20, "score": 90, "tag": "x"}, {"id": 21, "score": 90, "tag": "y"}]
    + [{"id": 30, "score": -5, "tag": "x"}, {"id": 31, "score": -5, "tag": "x"}, {"id": 32, "score": 0, "tag": "y"}]
)


def walk(entries, limit, **kwargs):
    ids, cursor, pages = [], None, 0
    while True:
        result = list_entries(entries, limit=limit, cursor=cursor, **kwargs)
        pages += 1
        ids.extend(item["id"] for item in result["items"])
        cursor = result["next_cursor"]
        if cursor is None:
            return ids, pages
        assert pages < 100


class ApiHiddenTests(unittest.TestCase):
    def test_every_page_size_visits_each_entry_once_in_order(self):
        expected = [e["id"] for e in sort_items(ENTRIES)]
        self.assertEqual(expected[:3], [20, 21, 1])
        for limit in range(1, len(ENTRIES) + 3):
            ids, _ = walk(ENTRIES, limit)
            self.assertEqual(ids, expected, f"limit={limit}")

    def test_filtered_walk(self):
        wanted = [e["id"] for e in sort_items(ENTRIES) if e["tag"] == "x"]
        for limit in (1, 2, 3, 5):
            ids, _ = walk(ENTRIES, limit, tag="x")
            self.assertEqual(ids, wanted)

    def test_total_ignores_paging_but_respects_filter(self):
        first = list_entries(ENTRIES, limit=3)
        self.assertEqual(first["total"], len(ENTRIES))
        later = list_entries(ENTRIES, limit=3, cursor=first["next_cursor"], tag="y")
        self.assertEqual(later["total"], sum(1 for e in ENTRIES if e["tag"] == "y"))

    def test_exact_multiple_has_no_extra_page(self):
        entries = [{"id": i, "score": 1, "tag": "t"} for i in range(1, 7)]
        ids, pages = walk(entries, 3)
        self.assertEqual((ids, pages), ([1, 2, 3, 4, 5, 6], 2))
        last = list_entries(entries, limit=3, cursor="1:3")
        self.assertIsNone(last["next_cursor"])

    def test_cursor_between_ties(self):
        result = list_entries(ENTRIES, limit=2, cursor="40:3")
        self.assertEqual([e["id"] for e in result["items"]], [4, 5])
        self.assertEqual(result["next_cursor"], "40:5")

    def test_negative_scores_in_cursor(self):
        result = list_entries(ENTRIES, limit=1, cursor="-5:30")
        self.assertEqual([e["id"] for e in result["items"]], [31])
        self.assertEqual(decode_cursor("-5:30"), (-5, 30))
        self.assertEqual(encode_cursor({"id": 3, "score": -5}), "-5:3")

    def test_empty_and_invalid(self):
        self.assertEqual(list_entries([], limit=5), {"items": [], "next_cursor": None, "total": 0})
        with self.assertRaises(ValueError):
            list_entries(ENTRIES, limit=0)
        with self.assertRaises(ValueError):
            list_entries(ENTRIES, cursor="nonsense")

    def test_is_after_and_page_helpers(self):
        self.assertTrue(is_after({"id": 5, "score": 40}, (40, 3)))
        self.assertFalse(is_after({"id": 3, "score": 40}, (40, 3)))
        self.assertFalse(is_after({"id": 1, "score": 40}, (40, 3)))
        self.assertFalse(is_after({"id": 99, "score": 41}, (40, 3)))
        self.assertTrue(is_after({"id": 1, "score": 39}, (40, 3)))
        chunk, more = page(sort_items(ENTRIES), (40, 6), 5)
        self.assertEqual([e["id"] for e in chunk], [7, 32, 30, 31])
        self.assertFalse(more)


if __name__ == "__main__":
    unittest.main()
