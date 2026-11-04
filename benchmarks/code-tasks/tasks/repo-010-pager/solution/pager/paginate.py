"""Paging through a list."""

from .cursor import decode_cursor, encode_cursor


def paginate(items, limit, cursor=None):
    """One page of ``items``.

    ``limit`` must be an int from 1 to 100 (a bool is not accepted), otherwise ValueError. ``cursor`` is ``None`` for the
    first page or a cursor returned by an earlier call; an invalid cursor, or one whose offset is greater than
    ``len(items)``, is a ValueError (an offset equal to ``len(items)`` is valid and gives an empty page).

    Returns ``{"items": <up to limit items from the offset>, "next": <cursor of the following page, or None when this
    page reaches the end of the list>, "total": len(items)}``.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be an int from 1 to 100")
    offset = 0 if cursor is None else decode_cursor(cursor)
    if offset > len(items):
        raise ValueError("cursor is past the end of the list")
    end = offset + limit
    return {
        "items": list(items[offset:end]),
        "next": encode_cursor(end) if end < len(items) else None,
        "total": len(items),
    }
