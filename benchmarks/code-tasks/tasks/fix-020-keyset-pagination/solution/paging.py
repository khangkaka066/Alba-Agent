"""Keyset (cursor) pagination over entries ordered by ``sorting.sort_key``."""

from sorting import sort_key


def is_after(item, cursor):
    """True when ``item`` sorts strictly after the position ``cursor``.

    ``cursor`` is the ``(score, id)`` pair of the last entry that was already returned.
    Entries that tie on score are ordered by id, so an entry with the same score and a
    larger id is still after the cursor.
    """
    cursor_score, cursor_id = cursor
    return sort_key(item) > (-cursor_score, cursor_id)


def page(sorted_items, cursor, limit):
    """Return ``(chunk, has_more)``.

    ``sorted_items`` is already in sort order. With ``cursor=None`` the page starts at
    the beginning, otherwise right after the cursor position. ``chunk`` holds at most
    ``limit`` entries and ``has_more`` says whether any entries remain after it.
    """
    remaining = [item for item in sorted_items if cursor is None or is_after(item, cursor)]
    return remaining[:limit], len(remaining) > limit
