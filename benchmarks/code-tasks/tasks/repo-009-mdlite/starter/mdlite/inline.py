"""Inline formatting."""

import re

from .html import escape

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_EM = re.compile(r"\*(.+?)\*")


def render_inline(text):
    """Escape ``text`` and turn the inline markers into HTML.

    ``\`code\``` becomes ``<code>code</code>`` and nothing inside a code span is formatted any further.
    ``**bold**`` becomes ``<strong>bold</strong>`` and ``*em*`` becomes ``<em>em</em>``. A marker without a partner is kept
    as it is. Bold and emphasis are not nested inside each other.
    """
    out = escape(text)
    out = _CODE.sub(lambda m: "<code>" + m.group(1) + "</code>", out)
    out = _BOLD.sub(lambda m: "<strong>" + m.group(1) + "</strong>", out)
    out = _EM.sub(lambda m: "<em>" + m.group(1) + "</em>", out)
    return out
