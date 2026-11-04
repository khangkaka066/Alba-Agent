import unittest

from csvlite import parse_csv, to_csv


class ParseTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_csv("a,b,c\n1,2,3\n"), [["a", "b", "c"], ["1", "2", "3"]])

    def test_empty_and_terminators(self):
        self.assertEqual(parse_csv(""), [])
        self.assertEqual(parse_csv("\n"), [])
        self.assertEqual(parse_csv("a,b"), [["a", "b"]])
        self.assertEqual(parse_csv("a,b\n"), [["a", "b"]])
        self.assertEqual(parse_csv("a,b\r\nc,d\r\n"), [["a", "b"], ["c", "d"]])
        self.assertEqual(parse_csv("a\nb\r\nc"), [["a"], ["b"], ["c"]])

    def test_blank_lines_skipped(self):
        self.assertEqual(parse_csv("a\n\n\nb\n"), [["a"], ["b"]])
        self.assertEqual(parse_csv("\r\na\r\n\r\nb"), [["a"], ["b"]])

    def test_empty_fields(self):
        self.assertEqual(parse_csv("a,b,\n"), [["a", "b", ""]])
        self.assertEqual(parse_csv(",\n"), [["", ""]])
        self.assertEqual(parse_csv(",,"), [["", "", ""]])
        self.assertEqual(parse_csv("a,,c"), [["a", "", "c"]])
        self.assertEqual(parse_csv(',a'), [["", "a"]])

    def test_whitespace_preserved(self):
        self.assertEqual(parse_csv(" a , b \n"), [[" a ", " b "]])

    def test_quoted_fields(self):
        self.assertEqual(parse_csv('"a,b",c\n'), [["a,b", "c"]])
        self.assertEqual(parse_csv('"say ""hi""",x'), [['say "hi"', "x"]])
        self.assertEqual(parse_csv('"",x'), [["", "x"]])
        self.assertEqual(parse_csv('""\n'), [[""]])
        self.assertEqual(parse_csv('""""'), [['"']])
        self.assertEqual(parse_csv('x,""'), [["x", ""]])

    def test_quoted_newlines_kept_verbatim(self):
        self.assertEqual(parse_csv('"line1\nline2",b\n'), [["line1\nline2", "b"]])
        self.assertEqual(parse_csv('"l1\r\nl2",b\r\nc,d'), [["l1\r\nl2", "b"], ["c", "d"]])
        self.assertEqual(parse_csv('"a\n\nb"'), [["a\n\nb"]])

    def test_quote_inside_unquoted_field_is_literal(self):
        self.assertEqual(parse_csv('ab"cd,e'), [['ab"cd', "e"]])
        self.assertEqual(parse_csv('5" pipe,x'), [['5" pipe', "x"]])
        self.assertEqual(parse_csv(' "a",b'), [[' "a"', "b"]])

    def test_lone_cr_is_ordinary(self):
        self.assertEqual(parse_csv("a\rb,c\n"), [["a\rb", "c"]])

    def test_custom_delimiter(self):
        self.assertEqual(parse_csv("a;b,c;d\n", ";"), [["a", "b,c", "d"]])
        self.assertEqual(parse_csv('"a;b";c', ";"), [["a;b", "c"]])
        self.assertEqual(parse_csv("a\tb\n", "\t"), [["a", "b"]])

    def test_malformed(self):
        for text in ['"abc', '"abc""', 'a,"b', '"a"b', '"a" ,b', '"a"\r"', '"a"x\n']:
            with self.assertRaises(ValueError, msg=text):
                parse_csv(text)

    def test_bad_delimiter(self):
        for d in ["", ",,", '"', "\n", "\r", None]:
            with self.assertRaises(ValueError, msg=repr(d)):
                parse_csv("", d)
            with self.assertRaises(ValueError, msg=repr(d)):
                to_csv([], d)


class WriteTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(to_csv([["a", "b"], ["c", "d"]]), "a,b\nc,d\n")
        self.assertEqual(to_csv([]), "")
        self.assertEqual(to_csv([["x", "", "z"]]), "x,,z\n")
        self.assertEqual(to_csv([["", ""]]), ",\n")

    def test_quoting(self):
        self.assertEqual(to_csv([["a,b", "c"]]), '"a,b",c\n')
        self.assertEqual(to_csv([['say "hi"']]), '"say ""hi"""\n')
        self.assertEqual(to_csv([["l1\nl2", "x"]]), '"l1\nl2",x\n')
        self.assertEqual(to_csv([["l1\rl2"]]), '"l1\rl2"\n')
        self.assertEqual(to_csv([["a;b", "c,d"]], ";"), '"a;b";c,d\n')

    def test_single_empty_field_row_is_quoted(self):
        self.assertEqual(to_csv([[""]]), '""\n')
        self.assertEqual(to_csv([["a"], [""], ["b"]]), 'a\n""\nb\n')

    def test_leading_trailing_spaces_untouched(self):
        self.assertEqual(to_csv([[" a ", "b "]]), " a ,b \n")

    def test_errors(self):
        with self.assertRaises(ValueError):
            to_csv([["a"], []])
        with self.assertRaises(TypeError):
            to_csv([["a", 1]])

    def test_roundtrip(self):
        rows = [
            ["id", "note"],
            ["1", 'He said "no", then left'],
            ["2", "multi\nline\r\ntext"],
            [""],
            ["", ""],
            ['"', '""', ","],
            [" spaced ", "tab\there"],
        ]
        self.assertEqual(parse_csv(to_csv(rows)), rows)
        self.assertEqual(parse_csv(to_csv(rows, "|"), "|"), rows)
        self.assertEqual(parse_csv(to_csv(rows, "\t"), "\t"), rows)


if __name__ == "__main__":
    unittest.main()
