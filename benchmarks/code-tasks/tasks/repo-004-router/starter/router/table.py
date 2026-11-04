"""Finding the handler for a request."""

from .path import compile_pattern


class RouteTable:
    def __init__(self):
        self._routes = []

    def add(self, method, pattern, handler):
        regex, names = compile_pattern(pattern)
        self._routes.append((method.upper(), regex, names, handler))

    def _candidates(self, path):
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        for method, regex, names, handler in self._routes:
            found = regex.match(path)
            if found:
                yield method, names, found.groups(), handler

    def match(self, method, path):
        """Return ``(handler, params)`` or ``None``.

        A single trailing "/" on ``path`` is ignored (except for the root path "/"). Among the routes
        whose method and pattern both match, the most specific wins: the one with the fewest
        ``<params>``; if still tied, the one registered first. ``params`` maps names to the matched text.
        """
        for found_method, names, values, handler in self._candidates(path):
            if found_method == method.upper():
                return handler, dict(zip(names, values))
        return None

    def allowed_methods(self, path):
        """Sorted list of the methods that have a route matching ``path``."""
        return sorted({found_method for found_method, _, _, _ in self._candidates(path)})
