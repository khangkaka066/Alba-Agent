import unittest

from errors import SqlError
from tokenizer import tokenize


class TokenizerTests(unittest.TestCase):
    def test_keywords_are_uppercased_and_identifiers_keep_case(self):
        self.assertEqual(tokenize("select Name from Users"), [("kw", "SELECT"), ("id", "Name"), ("kw", "FROM"), ("id", "Users")])

    def test_numbers_int_float_and_negative(self):
        self.assertEqual(tokenize("1 2.5 -3 -0.5"), [("num", 1), ("num", 2.5), ("num", -3), ("num", -0.5)])
        self.assertIsInstance(tokenize("7")[0][1], int)
        self.assertIsInstance(tokenize("7.0")[0][1], float)

    def test_strings_and_doubled_quotes(self):
        self.assertEqual(tokenize("'abc'"), [("str", "abc")])
        self.assertEqual(tokenize("'it''s'"), [("str", "it's")])
        self.assertEqual(tokenize("''"), [("str", "")])
        self.assertEqual(tokenize("'a b ( ; select'"), [("str", "a b ( ; select")])

    def test_operators_and_not_equal_spellings(self):
        self.assertEqual([v for _, v in tokenize("= != <> < <= > >=")], ["=", "!=", "!=", "<", "<=", ">", ">="])
        self.assertTrue(all(kind == "op" for kind, _ in tokenize("= != <> < <= > >=")))

    def test_punctuation(self):
        self.assertEqual(tokenize("(a,*);"), [("p", "("), ("id", "a"), ("p", ","), ("p", "*"), ("p", ")"), ("p", ";")])

    def test_whitespace_including_newlines_is_ignored(self):
        self.assertEqual(tokenize("\n  a \t b\n"), [("id", "a"), ("id", "b")])
        self.assertEqual(tokenize(""), [])

    def test_keyword_prefix_is_still_an_identifier(self):
        self.assertEqual(tokenize("selection integer"), [("id", "selection"), ("id", "integer")])
        self.assertEqual(tokenize("INT text"), [("kw", "INT"), ("kw", "TEXT")])

    def test_bad_input_raises_sql_error(self):
        for bad in ("'unterminated", "a @ b", "x # y", "a $"):
            with self.assertRaises(SqlError, msg=bad):
                tokenize(bad)


if __name__ == "__main__":
    unittest.main()
