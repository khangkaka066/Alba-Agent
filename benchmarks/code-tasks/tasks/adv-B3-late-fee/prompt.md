Implement `late_fee(due, paid, daily_cents)` in `latefee.py`, returning the late fee in whole cents as an `int`.

- `due` and `paid` are date strings in exactly the form `YYYY-MM-DD` (four digits, dash, two digits, dash, two digits). Any other string (`"20240115"`, `"2024-1-5"`, `"2024-02-30"`, `" 2024-01-15"`, ISO week dates, ...) raises `ValueError`; a non-`str` argument raises `TypeError`. Dates follow the real Gregorian calendar, so `2024-02-29` is valid and `2023-02-29` is not.
- `daily_cents` is an `int` of at least 0 (a `bool` is not accepted); anything else that is an `int` but negative, or a `bool`, raises `ValueError`.

Rules:
1. Effective due date: if `due` falls on a Saturday it moves to the following Monday; if on a Sunday it also moves to the following Monday. Otherwise it is unchanged.
2. Grace period: payment is free of fees through 5 calendar days after the effective due date, inclusive. Paying exactly 5 days after the effective due date costs nothing; paying 6 days after counts as 1 chargeable day.
3. Chargeable days = (days from the effective due date to `paid`) minus 5, never below 0, and capped at 30.
4. The fee is `chargeable_days * daily_cents`. Paying on or before the due date, or any time within the grace period, gives `0`.

Calendar day counts are real day counts (a February 29 counts as a day when it lies between the two dates).
