import unittest

from api import list_entries

ENTRIES = [
    {"id": 1, "score": 50, "tag": "a"},
    {"id": 2, "score": 70, "tag": "b"},
    {"id": 3, "score": 50, "tag": "a"},
    {"id": 4, "score": 50, "tag": "b"},
    {"id": 5, "score": 10, "tag": "a"},
]


def walk(limit, **kwargs):
    ids, cursor = [], None
    while True:
        result = list_entries(ENTRIES, limit=limit, cursor=cursor, **kwargs)
        ids.extend(item["id"] for item in result["items"])
        cursor = result["next_cursor"]
        if cursor is None:
            return ids


class ApiTests(unittest.TestCase):
    def test_first_page(self):
        result = list_entries(ENTRIES, limit=2)
        self.assertEqual([e["id"] for e in result["items"]], [2, 1])
        self.assertEqual(result["next_cursor"], "50:1")
        self.assertEqual(result["total"], 5)

    def test_walk_in_pages_of_two_visits_everything(self):
        self.assertEqual(walk(2), [2, 1, 3, 4, 5])

    def test_walk_with_tag_filter(self):
        self.assertEqual(walk(1, tag="a"), [1, 3, 5])


if __name__ == "__main__":
    unittest.main()
