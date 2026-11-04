"""Durations written by humans."""

import re

_PARTS = re.compile(r"(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?")


def parse_duration(text):
    """Return the number of seconds in ``text``.

    Accepted forms: a bare integer ("90" is 90 seconds) or any of the units ``h``, ``m``, ``s`` in
    that order, each at most once, optionally separated by whitespace: "1h30m", "45s", "2h", "1h 5m 10s".
    Surrounding whitespace is ignored. Anything else - empty text, unknown units, units out of order
    or repeated ("5x", "10s1h", "1h1h", "abc") - is a ValueError.
    """
    stripped = text.strip()
    if stripped.isascii() and stripped.isdigit():
        return int(stripped)
    match = _PARTS.fullmatch(stripped)
    if not stripped or match is None:
        raise ValueError(f"not a duration: {text!r}")
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds
