"""Render, summarise and apply line diffs produced by ``diff.diff_lines``."""

from diff import diff_lines


class PatchError(Exception):
    """The diff does not match the text it is applied to."""


def render(a, b):
    """Diff of ``a`` against ``b`` as text, one line per op prefixed ``"  "``, ``"- "`` or ``"+ "``."""
    prefix = {"=": "  ", "-": "- ", "+": "+ "}
    return "\n".join(prefix[op] + line for op, line in diff_lines(a, b))


def summarize(ops):
    """Count the ops: ``{"added": n, "removed": n, "unchanged": n}``."""
    return {
        "added": sum(1 for op, _ in ops if op == "+"),
        "removed": sum(1 for op, _ in ops if op == "-"),
        "unchanged": sum(1 for op, _ in ops if op == "="),
    }


def apply_ops(a, ops):
    """Apply ``ops`` to list ``a`` and return the new list.

    Every ``"="`` and ``"-"`` op must match the next unread line of ``a`` and all of ``a``
    must be consumed, otherwise PatchError is raised.
    """
    out = []
    pos = 0
    for op, line in ops:
        if op in ("=", "-"):
            if pos >= len(a) or a[pos] != line:
                raise PatchError(f"line {pos} does not match {line!r}")
            pos += 1
        if op in ("=", "+"):
            out.append(line)
    if pos != len(a):
        raise PatchError("diff does not cover the whole input")
    return out
