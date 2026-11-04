"""Public listing API for leaderboard entries."""

from paging import page
from sorting import sort_items


def encode_cursor(item):
    """Opaque text cursor for the position of ``item``: ``"<score>:<id>"``."""
    return f"{item['score']}:{item['id']}"


def decode_cursor(text):
    """Inverse of ``encode_cursor``; returns ``(score, id)`` or raises ValueError."""
    try:
        score_text, id_text = text.split(":")
        return int(score_text), int(id_text)
    except ValueError:
        raise ValueError(f"invalid cursor: {text!r}") from None


def list_entries(entries, limit=10, cursor=None, tag=None):
    """Return one page of entries as ``{"items", "next_cursor", "total"}``.

    ``tag`` (optional) keeps only entries whose ``tag`` equals it. ``total`` counts all
    entries that pass the filter, not just this page. ``next_cursor`` is the cursor of
    the last item on this page, or None when there is nothing after it. ``limit`` must
    be at least 1 (ValueError otherwise).
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    selected = [e for e in entries if tag is None or e["tag"] == tag]
    position = decode_cursor(cursor) if cursor is not None else None
    chunk, has_more = page(sort_items(selected), position, limit)
    next_cursor = encode_cursor(chunk[-1]) if chunk and has_more else None
    return {"items": chunk, "next_cursor": next_cursor, "total": len(selected)}
