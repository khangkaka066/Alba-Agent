"""Minimal {{placeholder}} templating for notification emails."""

import re

# A placeholder is {{name}}; the name is word characters and may be padded with spaces: {{ name }}.
PLACEHOLDER = re.compile(r"\{\{\s*(\w+?)\s*\}\}")


def placeholders(template):
    """Names used by the template, in order of first appearance, without duplicates."""
    names = []
    for name in PLACEHOLDER.findall(template):
        if name not in names:
            names.append(name)
    return names


def render(template, values):
    """Replace every placeholder with ``str(values[name])``.

    A placeholder whose name is not in ``values`` is left exactly as written.
    Text outside placeholders (including single braces) is never changed.
    """
    def lookup(match):
        name = match.group(1)
        if name in values:
            return str(values[name])
        return match.group(0)

    return PLACEHOLDER.sub(lookup, template)
