"""Timestamp parsing. Everything is normalised to timezone-aware UTC datetimes."""

from datetime import datetime, timezone


def utc_offset_minutes(dt: datetime) -> int:
    """Offset of `dt` from UTC in whole minutes (east of UTC is positive); 0 for naive datetimes."""
    offset = dt.utcoffset()
    if offset is None:
        return 0
    return int(offset.total_seconds() // 60)


def to_utc(dt: datetime) -> datetime:
    """Return the same instant as an aware UTC datetime. Naive datetimes are taken to be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_ts(text: str) -> datetime:
    """Parse an ISO-8601 timestamp (offset optional) to aware UTC."""
    return to_utc(datetime.fromisoformat(text))
