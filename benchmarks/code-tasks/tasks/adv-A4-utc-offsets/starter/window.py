"""Time windows over ISO-8601 timestamp strings."""

from tz import parse_ts


def minutes_between(start: str, end: str) -> int:
    """Whole minutes from `start` to `end` (negative if end is earlier)."""
    delta = parse_ts(end) - parse_ts(start)
    return int(delta.total_seconds() // 60)


def overlaps(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """True if half-open windows [a0, a1) and [b0, b1) share any instant."""
    a0, a1 = parse_ts(a[0]), parse_ts(a[1])
    b0, b1 = parse_ts(b[0]), parse_ts(b[1])
    return a0 < b1 and b0 < a1


def utc_date(text: str) -> str:
    """Calendar date (UTC) of the instant, as YYYY-MM-DD."""
    return parse_ts(text).date().isoformat()
