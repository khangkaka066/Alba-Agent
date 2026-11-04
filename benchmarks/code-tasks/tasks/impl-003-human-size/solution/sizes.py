import re
from fractions import Fraction

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)")


def format_size(num_bytes: int) -> str:
    if num_bytes < 0:
        raise ValueError("negative size")
    if num_bytes < 1024:
        return f"{num_bytes} B"
    idx = 1
    while idx < len(_UNITS) - 1 and num_bytes >= 1024 ** (idx + 1):
        idx += 1
    tenths = (num_bytes * 20 + 1024**idx) // (2 * 1024**idx)
    if tenths >= 10240 and idx < len(_UNITS) - 1:
        idx += 1
        tenths = 10
    return f"{tenths // 10}.{tenths % 10} {_UNITS[idx]}"


def parse_size(text: str) -> int:
    m = _PATTERN.fullmatch(text.strip())
    if m is None:
        raise ValueError(f"invalid size: {text!r}")
    unit = m.group(2).upper()
    if unit not in _UNITS:
        raise ValueError(f"unknown unit: {m.group(2)!r}")
    value = Fraction(m.group(1)) * 1024 ** _UNITS.index(unit)
    return int(value)
