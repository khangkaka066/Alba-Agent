import unittest

from router.app import App
from router.middleware import wrap
from router.path import compile_pattern


class PathTests(unittest.TestCase):
    def test_params_and_literals(self):
        regex, names = compile_pattern("/users/<id>/files/<name>.txt")
        self.assertEqual(names, ["id", "name"])
        self.assertEqual(regex.match("/users/7/files/a.txt").groups(), ("7", "a"))
        self.assertIsNone(regex.match("/users/7/files/a_txt"))
        self.assertIsNone(regex.match("/users/7/files/.txt"))
        self.assertIsNone(regex.match("/users/7/x/files/a.txt"))

    def test_regex_characters_in_patterns_are_literal(self):
        regex, _ = compile_pattern("/a+b/(c)/<x>")
        self.assertIsNotNone(regex.match("/a+b/(c)/z"))
        self.assertIsNone(regex.match("/aab/c/z"))
        regex, _ = compile_pattern("/v1.0/ping")
        self.assertIsNone(regex.match("/v1x0/ping"))

    def test_param_does_not_cross_segments(self):
        regex, _ = compile_pattern("/u/<id>")
        self.assertIsNone(regex.match("/u/1/2"))
        self.assertIsNone(regex.match("/u/"))


class MiddlewareTests(unittest.TestCase):
    def test_first_is_outermost(self):
        log = []

        def tag(name):
            def middleware(next_handler):
                def handler(**params):
                    log.append(f"{name} in")
                    result = next_handler(**params)
                    log.append(f"{name} out")
                    return result
                return handler
            return middleware

        wrapped = wrap(lambda: "done", [tag("a"), tag("b")])
        self.assertEqual(wrapped(), "done")
        self.assertEqual(log, ["a in", "b in", "b out", "a out"])

    def test_no_middlewares(self):
        handler = lambda: 1
        self.assertIs(wrap(handler, []), handler)


class AppTests(unittest.TestCase):
    def make(self):
        app = App()
        app.route("GET", "/users/<id>")(lambda id: f"user {id}")
        app.route("GET", "/users/me")(lambda: "me")
        app.route("POST", "/users/<id>")(lambda id: f"created {id}")
        app.route("GET", "/files/<name>.txt")(lambda name: f"file {name}")
        app.route("GET", "/")(lambda: "root")
        return app

    def test_specificity_independent_of_registration_order(self):
        app = self.make()
        self.assertEqual(app.handle("GET", "/users/me"), (200, "me"))
        self.assertEqual(app.handle("GET", "/users/7"), (200, "user 7"))
        reverse = App()
        reverse.route("GET", "/a/<x>/<y>")(lambda x, y: "two")
        reverse.route("GET", "/a/<x>/b")(lambda x: "one")
        reverse.route("GET", "/a/b/c")(lambda: "none")
        self.assertEqual(reverse.handle("GET", "/a/b/c"), (200, "none"))
        self.assertEqual(reverse.handle("GET", "/a/q/b"), (200, "one"))
        self.assertEqual(reverse.handle("GET", "/a/q/r"), (200, "two"))

    def test_equal_specificity_first_registered_wins(self):
        app = App()
        app.route("GET", "/p/<a>")(lambda a: "first")
        app.route("GET", "/p/<b>")(lambda b: "second")
        self.assertEqual(app.handle("GET", "/p/1"), (200, "first"))

    def test_trailing_slash(self):
        app = self.make()
        self.assertEqual(app.handle("GET", "/users/7/"), (200, "user 7"))
        self.assertEqual(app.handle("GET", "/"), (200, "root"))

    def test_methods_are_case_insensitive(self):
        self.assertEqual(self.make().handle("get", "/users/7"), (200, "user 7"))

    def test_404_and_405(self):
        app = self.make()
        self.assertEqual(app.handle("GET", "/nope"), (404, "not found"))
        self.assertEqual(app.handle("DELETE", "/users/7"), (405, "allowed: GET, POST"))
        self.assertEqual(app.handle("POST", "/files/a.txt"), (405, "allowed: GET"))
        self.assertEqual(app.handle("POST", "/files/a_txt"), (404, "not found"))

    def test_dots_in_pattern(self):
        app = self.make()
        self.assertEqual(app.handle("GET", "/files/a.txt"), (200, "file a"))
        self.assertEqual(app.handle("GET", "/files/a_txt"), (404, "not found"))

    def test_middleware_order_in_app(self):
        order = []

        def mw(name):
            def middleware(next_handler):
                def handler(**params):
                    order.append(name)
                    return next_handler(**params)
                return handler
            return middleware

        app = App([mw("first"), mw("second")])
        app.route("GET", "/x")(lambda: "x")
        self.assertEqual(app.handle("GET", "/x"), (200, "x"))
        self.assertEqual(order, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
