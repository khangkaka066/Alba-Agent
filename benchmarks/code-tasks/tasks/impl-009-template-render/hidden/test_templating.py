import unittest

from templating import render


class RenderTests(unittest.TestCase):
    def test_plain_text_and_simple_vars(self):
        self.assertEqual(render("no tags", {}), "no tags")
        self.assertEqual(render("Hello, {{name}}!", {"name": "Ann"}), "Hello, Ann!")
        self.assertEqual(render("{{ a }}-{{ b }}", {"a": 1, "b": 2.5}), "1-2.5")
        self.assertEqual(render("", {}), "")

    def test_dotted_and_index_paths(self):
        ctx = {"user": {"name": "Bo", "tags": ["x", "y"], "pos": (7, 8)}, "rows": [{"id": 5}]}
        self.assertEqual(render("{{ user.name }}", ctx), "Bo")
        self.assertEqual(render("{{ user.tags.1 }}/{{ user.pos.0 }}", ctx), "y/7")
        self.assertEqual(render("{{ rows.0.id }}", ctx), "5")

    def test_value_conversion(self):
        ctx = {"t": True, "n": None, "z": 0, "e": ""}
        self.assertEqual(render("[{{t}}][{{n}}][{{z}}][{{e}}]", ctx), "[True][][0][]")

    def test_missing_raises_key_error(self):
        for tpl, ctx in [("{{ x }}", {}), ("{{ a.b }}", {"a": {}}), ("{{ l.3 }}", {"l": [1]}),
                         ("{{ s.0 }}", {"s": "abc"}), ("{{ a.b }}", {"a": 5}), ("{{ x | upper }}", {})]:
            with self.subTest(tpl=tpl):
                with self.assertRaises(KeyError):
                    render(tpl, ctx)

    def test_upper_lower(self):
        self.assertEqual(render("{{ n | upper }} {{ n|lower }}", {"n": "MiXed"}), "MIXED mixed")
        self.assertEqual(render("{{ v | upper }}", {"v": None}), "")
        self.assertEqual(render("{{ v | upper }}", {"v": True}), "TRUE")

    def test_default_filter(self):
        self.assertEqual(render('{{ x | default:"anon" }}', {}), "anon")
        self.assertEqual(render('{{ x | default:"anon" }}', {"x": None}), "anon")
        self.assertEqual(render('{{ x | default:"anon" }}', {"x": "Zed"}), "Zed")
        self.assertEqual(render('{{ x | default:"anon" }}', {"x": ""}), "")
        self.assertEqual(render('{{ x | default:"anon" }}', {"x": 0}), "0")
        self.assertEqual(render('[{{ a.b.c | default:"" }}]', {}), "[]")

    def test_filter_chaining(self):
        self.assertEqual(render('{{ u.name | default:"guest" | upper }}', {}), "GUEST")
        self.assertEqual(render('{{ n | upper | lower }}', {"n": "Ab"}), "ab")
        self.assertEqual(render('{{ n | default:"x y" | upper | default:"z" }}', {}), "X Y")

    def test_escape(self):
        self.assertEqual(render(r"use \{{ name }} here", {}), "use {{ name }} here")
        self.assertEqual(render(r"\{{ a }} {{ a }}", {"a": 1}), "{{ a }} 1")
        self.assertEqual(render(r"{{ a }}\{{", {"a": 1}), "1{{")

    def test_adjacent_tags_and_single_braces(self):
        self.assertEqual(render("{{a}}{{b}}", {"a": "x", "b": "y"}), "xy")
        self.assertEqual(render("{ a } } {{a}} {", {"a": 1}), "{ a } } 1 {")

    def test_value_text_is_not_reparsed(self):
        self.assertEqual(render("{{ a }}", {"a": "{{ b }}"}), "{{ b }}")

    def test_errors(self):
        bad = ["{{ a", "x {{ ", "{{ }}", "{{}}", "{{ a b }}", "{{ 1a }}", "{{ a. }}", "{{ a | }}",
               "{{ a | shout }}", "{{ a | default:anon }}", "{{ a | default }}", "{{ .a }}", "{{ a..b }}"]
        for tpl in bad:
            with self.subTest(tpl=tpl):
                with self.assertRaises(ValueError):
                    render(tpl, {"a": "v"})


if __name__ == "__main__":
    unittest.main()
