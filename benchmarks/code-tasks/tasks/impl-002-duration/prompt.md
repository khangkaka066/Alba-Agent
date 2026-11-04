Implement `parse_duration` and `format_duration` in `duration.py`.

`parse_duration(text: str) -> int` converts a compact duration string into whole seconds.
- Units are `d` (86400 s), `h` (3600 s), `m` (60 s) and `s` (1 s). Units are lowercase and case-sensitive.
- The string is one or more `<digits><unit>` tokens, e.g. `"1h30m"` or `"2d 4h 5s"`. Any amount of whitespace (including none) may separate tokens, and the whole string may have leading/trailing whitespace.
- Units must appear in descending order (`d`, `h`, `m`, `s`) and each unit may appear at most once. Not every unit is required.
- Raise `ValueError` for: an empty or whitespace-only string, an unknown unit, a number with no unit, a unit with no number, a repeated unit, units out of order, a sign or decimal point, or any other stray text.

`format_duration(seconds: int) -> str` is the inverse.
- Break `seconds` into days, hours, minutes and seconds, drop every component that is zero, and join the rest with a single space, largest first: `3725` -> `"1h 2m 5s"`.
- Days are the largest unit and are never rolled up further: `90000` -> `"1d 1h"`, `100000000` -> `"1157d 9h 46m 40s"`.
- `0` -> `"0s"`.
- Raise `ValueError` if `seconds` is negative.

For every valid input, `format_duration(parse_duration(s))` is the canonical form of `s`, and `parse_duration(format_duration(n)) == n`.
