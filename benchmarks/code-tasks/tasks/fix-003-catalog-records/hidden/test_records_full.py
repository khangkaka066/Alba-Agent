import unittest

from records import build_many, build_record, has_tag, rename


class RecordsFullTests(unittest.TestCase):
    def test_default_tags_not_shared(self):
        for _ in range(3):
            self.assertEqual(build_record("x")["tags"], ["imported"])

    def test_records_do_not_share_lists(self):
        a = build_record("a")
        b = build_record("b")
        a["tags"].append("extra")
        self.assertEqual(b["tags"], ["imported"])
        self.assertEqual(build_record("c")["tags"], ["imported"])

    def test_callers_list_untouched(self):
        mine = ["fiction", "new"]
        record = build_record("novel", mine)
        self.assertEqual(mine, ["fiction", "new"])
        self.assertEqual(record["tags"], ["fiction", "new", "imported"])
        record["tags"].append("later")
        self.assertEqual(mine, ["fiction", "new"])

    def test_empty_list_given(self):
        mine = []
        self.assertEqual(build_record("n", mine)["tags"], ["imported"])
        self.assertEqual(mine, [])

    def test_build_many_with_tags(self):
        base = ["a"]
        records = build_many(["x", "y", "z"], base)
        self.assertEqual(base, ["a"])
        for record in records:
            self.assertEqual(record["tags"], ["a", "imported"])
        records[0]["tags"].append("only-x")
        self.assertEqual(records[1]["tags"], ["a", "imported"])

    def test_build_many_without_tags(self):
        records = build_many(["x", "y"])
        self.assertEqual([r["name"] for r in records], ["x", "y"])
        self.assertEqual([r["tags"] for r in records], [["imported"], ["imported"]])
        self.assertEqual(build_many(["z"])[0]["tags"], ["imported"])

    def test_rename_and_has_tag(self):
        original = build_record("old", ["t"])
        copy = rename(original, "new")
        copy["tags"].append("u")
        self.assertEqual(original["tags"], ["t", "imported"])
        self.assertEqual(copy["name"], "new")
        self.assertTrue(has_tag(copy, "u"))
        self.assertFalse(has_tag(original, "u"))


if __name__ == "__main__":
    unittest.main()
