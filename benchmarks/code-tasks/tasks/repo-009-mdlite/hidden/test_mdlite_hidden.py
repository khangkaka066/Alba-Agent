import unittest

from mdlite.blocks import render
from mdlite.html import escape
from mdlite.inline import render_inline


class EscapeTests(unittest.TestCase):
    def test_each_character_once(self):
        self.assertEqual(escape("a < b & c > d"), "a &lt; b &amp; c &gt; d")
        self.assertEqual(escape('say "hi"'), "say &quot;hi&quot;")
        self.assertEqual(escape("&lt;"), "&amp;lt;")
        self.assertEqual(escape("<&>"), "&lt;&amp;&gt;")
        self.assertEqual(escape(""), "")
        self.assertEqual(escape("plain"), "plain")


class InlineTests(unittest.TestCase):
    def test_basic_markers(self):
        self.assertEqual(render_inline("a **b** c"), "a <strong>b</strong> c")
        self.assertEqual(render_inline("a *b* c"), "a <em>b</em> c")
        self.assertEqual(render_inline("use `x`"), "use <code>x</code>")
        self.assertEqual(render_inline("*a* and **b** and `c`"), "<em>a</em> and <strong>b</strong> and <code>c</code>")

    def test_code_is_literal(self):
        self.assertEqual(render_inline("`**x**`"), "<code>**x**</code>")
        self.assertEqual(render_inline("`*a* *b*`"), "<code>*a* *b*</code>")
        self.assertEqual(render_inline("`<b>`"), "<code>&lt;b&gt;</code>")
        self.assertEqual(render_inline("**a** `**b**` **c**"), "<strong>a</strong> <code>**b**</code> <strong>c</strong>")

    def test_text_is_escaped(self):
        self.assertEqual(render_inline("1 < 2 & 3"), "1 &lt; 2 &amp; 3")
        self.assertEqual(render_inline("**<b>**"), "<strong>&lt;b&gt;</strong>")

    def test_unmatched_markers_stay(self):
        self.assertEqual(render_inline("**a"), "**a")
        self.assertEqual(render_inline("a * b"), "a * b")
        self.assertEqual(render_inline("`a"), "`a")

    def test_stars_do_not_span_a_code_span(self):
        self.assertEqual(render_inline("*a `b*` c"), "*a <code>b*</code> c")


class BlockTests(unittest.TestCase):
    def test_headings(self):
        for level in range(1, 7):
            self.assertEqual(render("#" * level + " Title"), f"<h{level}>Title</h{level}>")
        self.assertEqual(render("# **Big** one"), "<h1><strong>Big</strong> one</h1>")

    def test_not_headings(self):
        self.assertEqual(render("####### x"), "<p>####### x</p>")
        self.assertEqual(render("#nospace"), "<p>#nospace</p>")
        self.assertEqual(render("# a\nb"), "<p># a b</p>")
        self.assertEqual(render("#  "), "<p>#</p>")

    def test_lists(self):
        self.assertEqual(render("- a\n- b\n- c"), "<ul><li>a</li><li>b</li><li>c</li></ul>")
        self.assertEqual(render("- *a*\n- `b`"), "<ul><li><em>a</em></li><li><code>b</code></li></ul>")
        self.assertEqual(render("- a\n\n- b"), "<ul><li>a</li></ul>\n<ul><li>b</li></ul>")

    def test_mixed_block_is_a_paragraph(self):
        self.assertEqual(render("- a\nb"), "<p>- a b</p>")
        self.assertEqual(render("x\n- a"), "<p>x - a</p>")

    def test_paragraphs(self):
        self.assertEqual(render("one\ntwo\n\nthree"), "<p>one two</p>\n<p>three</p>")
        self.assertEqual(render("  padded  \n   lines  "), "<p>padded lines</p>")

    def test_blank_lines_with_whitespace_separate_blocks(self):
        self.assertEqual(render("a\n   \nb"), "<p>a</p>\n<p>b</p>")
        self.assertEqual(render("a\n\n\n\nb"), "<p>a</p>\n<p>b</p>")

    def test_empty(self):
        self.assertEqual(render(""), "")
        self.assertEqual(render("   \n\n  "), "")

    def test_document(self):
        text = "# Title\n\nSome *text* with `code`\nand more.\n\n- one\n- two\n\n## End"
        self.assertEqual(render(text), "\n".join([
            "<h1>Title</h1>",
            "<p>Some <em>text</em> with <code>code</code> and more.</p>",
            "<ul><li>one</li><li>two</li></ul>",
            "<h2>End</h2>",
        ]))

    def test_escaping_in_blocks(self):
        self.assertEqual(render("a < b"), "<p>a &lt; b</p>")
        self.assertEqual(render("# a & b"), "<h1>a &amp; b</h1>")


if __name__ == "__main__":
    unittest.main()
