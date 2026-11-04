import unittest

from jpath import PathSyntaxError, get_path, has_path, parse_path

DOC = {
    "order": {
        "id": 7,
        "items": [{"sku": "A1", "qty": 2}, {"sku": "B2", "qty": 1, "note": None}],
        "a.b": "dotted",
        "0": "zero-key",
        "": "empty-key",
        'q"uote': "quoted",
        "back\\slash": "bs",
    },
    "tags": ["x", "y", "z"],
    "matrix": [[1, 2], [3, 4]],
    "flag": False,
    "nothing": None,
}


class PathTests(unittest.TestCase):
    def test_parse_basic(self):
        self.assertEqual(parse_path(""), [])
        self.assertEqual(parse_path("a"), ["a"])
        self.assertEqual(parse_path("a.b.c"), ["a", "b", "c"])
        self.assertEqual(parse_path("a.b[0]"), ["a", "b", 0])
        self.assertEqual(parse_path("[0].name"), [0, "name"])
        self.assertEqual(parse_path("m[1][-2]"), ["m", 1, -2])
        self.assertEqual(parse_path("a.0"), ["a", "0"])
        self.assertEqual(parse_path("first name.x y"), ["first name", "x y"])

    def test_parse_quoted(self):
        self.assertEqual(parse_path('a["x.y"]'), ["a", "x.y"])
        self.assertEqual(parse_path('["a"]["b"].c'), ["a", "b", "c"])
        self.assertEqual(parse_path('[""]'), [""])
        self.assertEqual(parse_path(r'["q\"uote"]'), ['q"uote'])
        self.assertEqual(parse_path(r'["back\\slash"]'), ["back\\slash"])
        self.assertEqual(parse_path('["a]b"]'), ["a]b"])
        self.assertEqual(parse_path('["0"]'), ["0"])

    def test_syntax_errors(self):
        bad = [
            ".a", "a.", "a..b", "a.[0]", "a[0", "a[]", "a[abc]", "a[-]", "a[1.5]", "a[0]b",
            "a]", "[0]]", 'a"b', '["a"', '["a]', r'["a\n"]', '["a"b]', "a[ 0]", "a[+1]", "..",
            "[", "]", ".", "a.b.", '["a"]x', "a[-]",
        ]
        for path in bad:
            with self.assertRaises(PathSyntaxError, msg=path):
                parse_path(path)
        self.assertTrue(issubclass(PathSyntaxError, ValueError))

    def test_get_simple(self):
        self.assertEqual(get_path(DOC, "order.id"), 7)
        self.assertEqual(get_path(DOC, "order.items[0].sku"), "A1")
        self.assertEqual(get_path(DOC, "order.items[1].qty"), 1)
        self.assertEqual(get_path(DOC, "tags[-1]"), "z")
        self.assertEqual(get_path(DOC, "matrix[1][0]"), 3)
        self.assertEqual(get_path(DOC, "tags"), ["x", "y", "z"])
        self.assertEqual(get_path(DOC, ""), DOC)
        self.assertEqual(get_path([10, 20], "[1]"), 20)

    def test_get_quoted_and_odd_keys(self):
        self.assertEqual(get_path(DOC, 'order["a.b"]'), "dotted")
        self.assertEqual(get_path(DOC, "order.0"), "zero-key")
        self.assertEqual(get_path(DOC, 'order[""]'), "empty-key")
        self.assertEqual(get_path(DOC, r'order["q\"uote"]'), "quoted")
        self.assertEqual(get_path(DOC, r'order["back\\slash"]'), "bs")

    def test_get_missing_returns_default(self):
        self.assertIsNone(get_path(DOC, "order.nope"))
        self.assertEqual(get_path(DOC, "order.nope", default="d"), "d")
        self.assertEqual(get_path(DOC, "tags[3]", default=-1), -1)
        self.assertEqual(get_path(DOC, "tags[-4]", default=-1), -1)
        self.assertEqual(get_path(DOC, "tags.x", default="d"), "d")  # str step on a list
        self.assertEqual(get_path(DOC, "order[0]", default="d"), "d")  # int step on a dict
        self.assertEqual(get_path(DOC, "order.id.deeper", default="d"), "d")
        self.assertEqual(get_path(DOC, "order.items[5].sku", default="d"), "d")
        self.assertEqual(get_path(DOC, "nothing.a", default="d"), "d")

    def test_none_value_is_not_default(self):
        self.assertIsNone(get_path(DOC, "nothing", default="d"))
        self.assertIsNone(get_path(DOC, "order.items[1].note", default="d"))
        self.assertIs(get_path(DOC, "flag", default="d"), False)

    def test_only_dicts_and_lists_are_traversed(self):
        self.assertEqual(get_path({"t": (1, 2)}, "t[0]", default="d"), "d")
        self.assertEqual(get_path({"s": "abc"}, "s[0]", default="d"), "d")
        self.assertEqual(get_path("abc", "[0]", default="d"), "d")

    def test_syntax_error_beats_missing(self):
        with self.assertRaises(PathSyntaxError):
            get_path({}, "a..b")
        with self.assertRaises(PathSyntaxError):
            get_path(DOC, "order.id[", default=5)
        with self.assertRaises(PathSyntaxError):
            has_path({}, "[x]")

    def test_has_path(self):
        self.assertTrue(has_path(DOC, "order.items[1].note"))
        self.assertTrue(has_path(DOC, "nothing"))
        self.assertTrue(has_path(DOC, ""))
        self.assertTrue(has_path(DOC, "tags[-3]"))
        self.assertFalse(has_path(DOC, "tags[3]"))
        self.assertFalse(has_path(DOC, "order.items[0].note"))
        self.assertFalse(has_path(DOC, "nothing.x"))
        self.assertTrue(has_path(None, ""))


if __name__ == "__main__":
    unittest.main()
