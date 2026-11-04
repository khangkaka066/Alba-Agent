import csv
import io
import unittest

from fields import format_field, needs_quotes, to_text
from table import format_row, write_table


def read_back(text, delimiter):
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))


class TableHiddenTests(unittest.TestCase):
    def test_round_trip_with_every_delimiter(self):
        header = ["a", "b", "c"]
        rows = [
            ["plain", "with;semi", "with,comma"],
            ['say "hi"', "tab\there", "  padded"],
            ["line\nbreak", "cr\rhere", "x|y"],
            ["", "trailing ", "p|q;r,s"],
        ]
        for delimiter in (",", ";", "\t", "|"):
            text = write_table(header, rows, delimiter=delimiter)
            self.assertEqual(read_back(text, delimiter), [header] + rows, repr(delimiter))

    def test_needs_quotes_depends_on_delimiter(self):
        self.assertTrue(needs_quotes("a;b", ";"))
        self.assertFalse(needs_quotes("a,b", ";"))
        self.assertTrue(needs_quotes("a,b", ","))
        self.assertFalse(needs_quotes("a;b", ","))
        self.assertTrue(needs_quotes("a|b", "|"))

    def test_other_quote_triggers(self):
        for text in ('a"b', "a\nb", "a\rb", " a", "a "):
            self.assertTrue(needs_quotes(text, ";"), repr(text))
        self.assertFalse(needs_quotes("a b", ";"))
        self.assertFalse(needs_quotes("", ";"))

    def test_inner_quotes_doubled(self):
        self.assertEqual(format_field('5" pipe', ";"), '"5"" pipe"')

    def test_to_text(self):
        self.assertEqual(to_text(None), "")
        self.assertEqual(to_text(True), "true")
        self.assertEqual(to_text(False), "false")
        self.assertEqual(to_text(3.5), "3.5")
        self.assertEqual(to_text(0), "0")

    def test_row_formatting_and_values(self):
        self.assertEqual(format_row([1, None, True, "a;b"], ";"), '1;;true;"a;b"')
        self.assertEqual(format_row(["a;b", "c"], ","), "a;b,c")

    def test_write_table_shape_and_validation(self):
        self.assertEqual(write_table(["h"], []), "h\r\n")
        with self.assertRaises(ValueError):
            write_table(["a", "b"], [[1]])
        with self.assertRaises(ValueError):
            write_table(["a"], [[1, 2]], delimiter=";")

    def test_tab_delimited_field_with_tab_is_quoted(self):
        self.assertEqual(write_table(["a", "b"], [["x\ty", "z"]], delimiter="\t"), 'a\tb\r\n"x\ty"\tz\r\n')


if __name__ == "__main__":
    unittest.main()
