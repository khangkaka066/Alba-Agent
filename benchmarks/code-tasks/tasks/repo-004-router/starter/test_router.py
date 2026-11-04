import unittest

from router.app import App
from router.path import compile_pattern


class RouterTests(unittest.TestCase):
    def test_dots_are_literal(self):
        regex, _ = compile_pattern("/files/<name>.txt")
        self.assertIsNotNone(regex.match("/files/a.txt"))
        self.assertIsNone(regex.match("/files/a_txt"))

    def test_static_beats_param(self):
        app = App()
        app.route("GET", "/users/<id>")(lambda id: f"user {id}")
        app.route("GET", "/users/me")(lambda: "me")
        self.assertEqual(app.handle("GET", "/users/me"), (200, "me"))
        self.assertEqual(app.handle("GET", "/users/7"), (200, "user 7"))

    def test_method_not_allowed(self):
        app = App()
        app.route("GET", "/x")(lambda: "x")
        self.assertEqual(app.handle("POST", "/x"), (405, "allowed: GET"))
        self.assertEqual(app.handle("GET", "/nope"), (404, "not found"))


if __name__ == "__main__":
    unittest.main()
