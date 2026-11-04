"""Block structure."""

import re

from .inline import render_inline

_HEADING = re.compile(r"(#{1,6}) (.*)")


def render(text):
    """Render a small markdown subset to HTML.

    The text is split into blocks at blank lines (lines that are empty or only whitespace); every line is stripped of
    surrounding whitespace first. A block is, in this order:

    * a heading when it is a single line that starts with one to six ``#``, a space and the heading text:
      ``<h2>text</h2>`` where the number is the count of ``#``. Seven or more ``#`` do not make a heading;
    * a list when every line of it starts with ``"- "``: ``<ul><li>item</li><li>item</li></ul>`` with one ``<ul>`` for the
      whole block;
    * otherwise a paragraph: its lines joined with a single space, as ``<p>text</p>``.

    Text goes through ``render_inline``. Blocks are joined with a newline; empty or blank input gives ``""``.
    """
    blocks = []
    for raw in re.split(r"\n\s*\n", text.strip("\n")):
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        if not lines:
            continue
        heading = _HEADING.fullmatch(lines[0]) if len(lines) == 1 else None
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
        elif all(line.startswith("- ") for line in lines):
            items = "".join(f"<li>{render_inline(line[2:])}</li>" for line in lines)
            blocks.append(f"<ul>{items}</ul>")
        else:
            blocks.append("<p>" + render_inline(" ".join(lines)) + "</p>")
    return "\n".join(blocks)
