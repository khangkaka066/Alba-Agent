import unittest

from templating import placeholders, render


class TemplatingFullTests(unittest.TestCase):
    def test_two_on_one_line(self):
        self.assertEqual(render("Hi {{first}} {{last}}!", {"first": "Ada", "last": "Lovelace"}), "Hi Ada Lovelace!")

    def test_adjacent(self):
        self.assertEqual(render("{{a}}{{b}}", {"a": 1, "b": 2}), "12")

    def test_text_between_placeholders_preserved(self):
        self.assertEqual(render("{{a}} and {{b}}", {"a": "x", "b": "y"}), "x and y")

    def test_spaces_inside_braces(self):
        self.assertEqual(render("[{{ name }}] [{{name }}] [{{  name}}]", {"name": "N"}), "[N] [N] [N]")

    def test_unknown_left_as_written(self):
        self.assertEqual(render("{{a}} {{ nope }} {{b}}", {"a": 1, "b": 2}), "1 {{ nope }} 2")

    def test_repeated_placeholder(self):
        self.assertEqual(render("{{x}}-{{x}}", {"x": "z"}), "z-z")

    def test_single_braces_untouched(self):
        self.assertEqual(render("{a} {{b}} {c}", {"b": "B"}), "{a} B {c}")

    def test_non_string_values(self):
        self.assertEqual(render("n={{n}} ok={{ok}}", {"n": 3, "ok": True}), "n=3 ok=True")

    def test_no_placeholders(self):
        self.assertEqual(render("plain text", {"a": 1}), "plain text")

    def test_names(self):
        self.assertEqual(placeholders("{{a}} and {{b}}"), ["a", "b"])
        self.assertEqual(placeholders("{{ b }} {{a}} {{b}}"), ["b", "a"])
        self.assertEqual(placeholders("nothing {here}"), [])

    def test_names_adjacent(self):
        self.assertEqual(placeholders("{{x}}{{y}}{{x}}"), ["x", "y"])


if __name__ == "__main__":
    unittest.main()
