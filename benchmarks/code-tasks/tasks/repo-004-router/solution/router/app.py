"""The application object."""

from .middleware import wrap
from .table import RouteTable


class App:
    def __init__(self, middlewares=()):
        self.routes = RouteTable()
        self.middlewares = list(middlewares)

    def route(self, method, pattern):
        def register(handler):
            self.routes.add(method, pattern, handler)
            return handler
        return register

    def handle(self, method, path):
        """Return ``(status, body)``.

        A matching route gives ``(200, wrap(handler, middlewares)(**params))``. If no route matches
        the path for any method the answer is ``(404, "not found")``; if the path matches only
        under other methods it is ``(405, "allowed: GET, POST")`` listing the allowed methods
        (sorted, comma and space separated).
        """
        found = self.routes.match(method, path)
        if found is None:
            allowed = self.routes.allowed_methods(path)
            if not allowed:
                return 404, "not found"
            return 405, "allowed: " + ", ".join(allowed)
        handler, params = found
        return 200, wrap(handler, self.middlewares)(**params)
