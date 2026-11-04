import unittest

from mdlite.blocks import render
from mdlite.html import escape
from mdlite.inline import render_inline


class MdliteTests(unittest.TestCase):
    def test_escape_does_not_double_escape(self):
        self.assertEqual(escape("a < b & c"), "a &lt; b &amp; c")

    def test_code_is_not_formatted(self):
        self.assertEqual(render_inline("`**x**`"), "<code>**x**</code>")

    def test_one_list_per_block(self):
        self.assertEqual(render("- a\n- b"), "<ul><li>a</li><li>b</li></ul>")

    def test_paragraph_lines_join_with_a_space(self):
        self.assertEqual(render("one\ntwo"), "<p>one two</p>")

    def test_seven_hashes_are_not_a_heading(self):
        self.assertEqual(render("####### x"), "<p>####### x</p>")


if __name__ == "__main__":
    unittest.main()
