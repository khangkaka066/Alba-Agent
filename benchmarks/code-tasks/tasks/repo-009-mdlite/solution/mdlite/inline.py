"""Inline formatting."""

import re

from .html import escape

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_EM = re.compile(r"\*(.+?)\*")


def _format(text):
    text = _BOLD.sub(lambda m: "<strong>" + m.group(1) + "</strong>", text)
    return _EM.sub(lambda m: "<em>" + m.group(1) + "</em>", text)


def render_inline(text):
    """Escape ``text`` and turn the inline markers into HTML.

    ``\`code\``` becomes ``<code>code</code>`` and nothing inside a code span is formatted any further.
    ``**bold**`` becomes ``<strong>bold</strong>`` and ``*em*`` becomes ``<em>em</em>``. A marker without a partner is kept
    as it is. Bold and emphasis are not nested inside each other.
    """
    escaped = escape(text)
    pieces = []
    position = 0
    for match in _CODE.finditer(escaped):
        pieces.append(_format(escaped[position:match.start()]))
        pieces.append("<code>" + match.group(1) + "</code>")
        position = match.end()
    pieces.append(_format(escaped[position:]))
    return "".join(pieces)
