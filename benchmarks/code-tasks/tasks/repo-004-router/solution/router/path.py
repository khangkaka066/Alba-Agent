"""Route patterns."""

import re


def compile_pattern(pattern):
    """Turn a pattern such as "/users/<id>/files/<name>.txt" into ``(regex, names)``.

    ``<x>`` matches one non-empty path segment part (no "/") and is reported under the name ``x``;
    every other character of the pattern, dots included, must match literally. The regex matches
    the whole path.
    """
    names = []
    parts = []
    position = 0
    for match in re.finditer(r"<(\w+)>", pattern):
        parts.append(re.escape(pattern[position:match.start()]))
        parts.append("([^/]+)")
        names.append(match.group(1))
        position = match.end()
    parts.append(re.escape(pattern[position:]))
    return re.compile("^" + "".join(parts) + "$"), names
