import unittest

from brackets import find_bracket_error, is_balanced


class BracketTests(unittest.TestCase):
    def test_balanced(self):
        for text in ["", "no brackets", "()", "([]{})", "f(a[1], {b: (2)})", "{\n  [\n  ]\n}"]:
            self.assertIsNone(find_bracket_error(text), text)
            self.assertTrue(is_balanced(text), text)

    def test_unexpected_closer(self):
        self.assertEqual(find_bracket_error(")"), ("unexpected_closer", 0))
        self.assertEqual(find_bracket_error("(a))"), ("unexpected_closer", 3))
        self.assertEqual(find_bracket_error("ab ]"), ("unexpected_closer", 3))
        self.assertFalse(is_balanced("}"))

    def test_mismatched(self):
        self.assertEqual(find_bracket_error("(]"), ("mismatched", 1))
        self.assertEqual(find_bracket_error("{[}]"), ("mismatched", 2))
        self.assertEqual(find_bracket_error("a(b[c)d]"), ("mismatched", 5))

    def test_unclosed_reports_innermost(self):
        self.assertEqual(find_bracket_error("("), ("unclosed", 0))
        self.assertEqual(find_bracket_error("{[("), ("unclosed", 2))
        self.assertEqual(find_bracket_error("(a) {b [c"), ("unclosed", 7))
        self.assertEqual(find_bracket_error("([)"), ("mismatched", 2))

    def test_first_problem_wins(self):
        self.assertEqual(find_bracket_error("(] )"), ("mismatched", 1))
        self.assertEqual(find_bracket_error(") ("), ("unexpected_closer", 0))

    def test_strings_are_ignored(self):
        self.assertIsNone(find_bracket_error('print("(")'))
        self.assertIsNone(find_bracket_error("x = '}' + \"]\""))
        self.assertIsNone(find_bracket_error(r'f("a\"(", 1)'))
        self.assertIsNone(find_bracket_error(r"f('\\')"))
        self.assertIsNone(find_bracket_error("f(\"it's\")"))
        self.assertEqual(find_bracket_error('("a)'), ("unterminated_string", 1))

    def test_escaped_backslash_then_quote_ends_string(self):
        # the string is "\\" (an escaped backslash); the closing quote is real
        self.assertEqual(find_bracket_error(r'("\\")'), None)
        self.assertEqual(find_bracket_error(r'("\\" ]'), ("mismatched", 6))

    def test_unterminated_strings(self):
        self.assertEqual(find_bracket_error('a "b'), ("unterminated_string", 2))
        self.assertEqual(find_bracket_error("(\n'abc\n)"), ("unterminated_string", 2))
        self.assertEqual(find_bracket_error("'abc\\"), ("unterminated_string", 0))
        self.assertEqual(find_bracket_error("( 'x"), ("unterminated_string", 2))

    def test_unterminated_string_beats_unclosed(self):
        self.assertEqual(find_bracket_error("(("+'"x'), ("unterminated_string", 2))

    def test_comments(self):
        self.assertIsNone(find_bracket_error("(a) # ) ( ]"))
        self.assertIsNone(find_bracket_error("(\n# }\n)"))
        self.assertEqual(find_bracket_error("# ok\n)"), ("unexpected_closer", 5))
        self.assertIsNone(find_bracket_error('"#" ()'))
        self.assertIsNone(find_bracket_error("# 'unterminated"))

    def test_hash_inside_string_is_not_comment(self):
        self.assertEqual(find_bracket_error('("#") ]'), ("unexpected_closer", 6))


if __name__ == "__main__":
    unittest.main()
