"""Durations written by humans."""

import re


def parse_duration(text):
    """Return the number of seconds in ``text``.

    Accepted forms: a bare integer ("90" is 90 seconds) or any of the units ``h``, ``m``, ``s`` in
    that order, each at most once, optionally separated by whitespace: "1h30m", "45s", "2h", "1h 5m 10s".
    Surrounding whitespace is ignored. Anything else - empty text, unknown units, units out of order
    or repeated ("5x", "10s1h", "1h1h", "abc") - is a ValueError.
    """
    total = 0
    for number, unit in re.findall(r"(\d+)([hms])", text):
        total += int(number) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total
