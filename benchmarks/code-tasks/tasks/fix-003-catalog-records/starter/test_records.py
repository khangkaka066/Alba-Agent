import unittest

from records import build_record


class RecordTests(unittest.TestCase):
    def test_default_tags_not_shared(self):
        first = build_record("a")
        second = build_record("b")
        self.assertEqual(first["tags"], ["imported"])
        self.assertEqual(second["tags"], ["imported"])

    def test_callers_list_untouched(self):
        mine = ["fiction"]
        record = build_record("novel", mine)
        self.assertEqual(mine, ["fiction"])
        self.assertEqual(record["tags"], ["fiction", "imported"])


if __name__ == "__main__":
    unittest.main()
