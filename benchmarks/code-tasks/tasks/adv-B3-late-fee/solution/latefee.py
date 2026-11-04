from __future__ import annotations

import re
from datetime import date, timedelta

_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_GRACE_DAYS = 5
_MAX_CHARGED_DAYS = 30


def _parse(value: object) -> date:
    if not isinstance(value, str):
        raise TypeError(f"date must be a str, got {type(value).__name__}")
    if not _FORMAT.fullmatch(value):
        raise ValueError(f"date must look like YYYY-MM-DD: {value!r}")
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)  # raises ValueError for impossible dates


def late_fee(due: str, paid: str, daily_cents: int) -> int:
    due_date = _parse(due)
    paid_date = _parse(paid)
    if isinstance(daily_cents, bool) or not isinstance(daily_cents, int) or daily_cents < 0:
        raise ValueError("daily_cents must be a non-negative int")
    weekday = due_date.weekday()  # Monday == 0
    if weekday >= 5:
        due_date += timedelta(days=7 - weekday)
    late_days = (paid_date - due_date).days
    chargeable = min(max(late_days - _GRACE_DAYS, 0), _MAX_CHARGED_DAYS)
    return chargeable * daily_cents
