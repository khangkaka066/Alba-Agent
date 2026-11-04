import unittest

from inifile import get_bool, parse_ini


class ParseTests(unittest.TestCase):
    def test_basic_sections(self):
        text = "[server]\nhost = example.org\nport=8080\n\n[db]\nname: main\n"
        self.assertEqual(
            parse_ini(text),
            {"server": {"host": "example.org", "port": "8080"}, "db": {"name": "main"}},
        )

    def test_comments_and_blank_lines(self):
        text = "; top\n# also\n[a]\n  ; indented comment\nk = v ; not a comment\n\n#x=1\n"
        self.assertEqual(parse_ini(text), {"a": {"k": "v ; not a comment"}})

    def test_global_keys_section_is_empty_string(self):
        self.assertEqual(parse_ini("a=1\n[s]\nb=2"), {"": {"a": "1"}, "s": {"b": "2"}})
        self.assertEqual(parse_ini("[s]\nb=2"), {"s": {"b": "2"}})
        self.assertEqual(parse_ini("; nothing\n"), {})
        self.assertEqual(parse_ini(""), {})

    def test_first_separator_wins(self):
        self.assertEqual(
            parse_ini("[u]\nurl = http://x.y/?a=b\ntime: 12:30\nweird=a:b"),
            {"u": {"url": "http://x.y/?a=b", "time": "12:30", "weird": "a:b"}},
        )

    def test_quotes_stripped(self):
        text = '[q]\na = "  padded  "\nb = ""\nc = "unterminated\nd = "\ne = ""x""\n'
        self.assertEqual(
            parse_ini(text),
            {"q": {"a": "  padded  ", "b": "", "c": '"unterminated', "d": '"', "e": '"x"'}},
        )

    def test_empty_value_and_duplicates(self):
        text = "[s]\nk =\nk2 = 1\nk2 = 2\n[t]\n[s]\nk3 = 3"
        self.assertEqual(parse_ini(text), {"s": {"k": "", "k2": "2", "k3": "3"}, "t": {}})

    def test_section_order_and_name_stripping(self):
        result = parse_ini("[ b ]\nx=1\n[a]\ny=2\n[ b ]\nz=3")
        self.assertEqual(list(result), ["b", "a"])
        self.assertEqual(result["b"], {"x": "1", "z": "3"})

    def test_crlf_and_case_sensitivity(self):
        result = parse_ini("[Main]\r\nKey = V\r\nkey = v\r\n")
        self.assertEqual(result, {"Main": {"Key": "V", "key": "v"}})

    def test_errors_report_line_numbers(self):
        cases = {
            "[a]\nk=v\nnonsense\n": "line 3",
            "[a\nk=v": "line 1",
            "k=v\n\n[]\n": "line 3",
            "[a]\n= value": "line 2",
            "[a]\n   : value": "line 2",
            "[  ]": "line 1",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as ctx:
                    parse_ini(text)
                self.assertIn(expected, str(ctx.exception))


class GetBoolTests(unittest.TestCase):
    def setUp(self):
        self.cfg = parse_ini("[f]\na=Yes\nb = off\nc=maybe\nd=1\ne=TRUE\n")

    def test_values(self):
        self.assertIs(get_bool(self.cfg, "f", "a"), True)
        self.assertIs(get_bool(self.cfg, "f", "b"), False)
        self.assertIs(get_bool(self.cfg, "f", "d"), True)
        self.assertIs(get_bool(self.cfg, "f", "e"), True)

    def test_defaults(self):
        self.assertIsNone(get_bool(self.cfg, "f", "missing"))
        self.assertIs(get_bool(self.cfg, "nosection", "a", True), True)
        self.assertIs(get_bool(self.cfg, "f", "missing", False), False)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            get_bool(self.cfg, "f", "c")
        with self.assertRaises(ValueError):
            get_bool({"s": {"k": ""}}, "s", "k")


if __name__ == "__main__":
    unittest.main()
