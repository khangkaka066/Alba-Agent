"""Opaque page cursors."""

import base64
import json


def encode_cursor(offset):
    """URL-safe base64 (without ``=`` padding) of the JSON text ``{"o": offset}`` written with no spaces."""
    raw = json.dumps({"o": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(text):
    """The offset stored in a cursor made by ``encode_cursor``.

    Anything that is not such a cursor is a ValueError: text that is not valid base64 or JSON, JSON that is not an
    object with exactly the key ``"o"``, and an offset that is not an int (a bool is not an int here) or is negative.
    """
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        data = json.loads(raw)
    except Exception as error:
        raise ValueError("invalid cursor") from error
    if not isinstance(data, dict) or set(data) != {"o"}:
        raise ValueError("invalid cursor")
    offset = data["o"]
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("invalid cursor")
    return offset
