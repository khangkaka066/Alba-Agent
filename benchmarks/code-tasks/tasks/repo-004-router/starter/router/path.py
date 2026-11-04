"""Route patterns."""

import re


def compile_pattern(pattern):
    """Turn a pattern such as "/users/<id>/files/<name>.txt" into ``(regex, names)``.

    ``<x>`` matches one non-empty path segment part (no "/") and is reported under the name ``x``;
    every other character of the pattern, dots included, must match literally. The regex matches
    the whole path.
    """
    names = []

    def capture(match):
        names.append(match.group(1))
        return "([^/]+)"

    return re.compile("^" + re.sub(r"<(\w+)>", capture, pattern) + "$"), names
