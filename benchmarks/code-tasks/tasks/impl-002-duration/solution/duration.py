import re

_UNITS = (("d", 86400), ("h", 3600), ("m", 60), ("s", 1))
_TOKEN = re.compile(r"([0-9]+)([a-zA-Z]+)\s*")


def parse_duration(text: str) -> int:
    text = text.strip()
    if not text:
        raise ValueError("empty duration")
    order = [u for u, _ in _UNITS]
    factors = dict(_UNITS)
    pos = 0
    last = -1
    total = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise ValueError(f"invalid duration: {text!r}")
        unit = m.group(2)
        if unit not in factors:
            raise ValueError(f"unknown unit {unit!r}")
        idx = order.index(unit)
        if idx <= last:
            raise ValueError("units repeated or out of order")
        last = idx
        total += int(m.group(1)) * factors[unit]
        pos = m.end()
    return total


def format_duration(seconds: int) -> str:
    if seconds < 0:
        raise ValueError("negative duration")
    if seconds == 0:
        return "0s"
    parts = []
    for unit, size in _UNITS:
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count}{unit}")
    return " ".join(parts)
