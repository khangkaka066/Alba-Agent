Implement `format_size` and `parse_size` in `sizes.py`. All units are binary (1 KB = 1024 B).

`format_size(num_bytes: int) -> str`
- Units, in order: `B`, `KB`, `MB`, `GB`, `TB`, `PB`. `PB` is the largest; larger values stay in `PB` (e.g. `"2048.0 PB"`).
- Values below 1024 are shown as an integer followed by ` B`: `0` -> `"0 B"`, `1023` -> `"1023 B"`.
- Otherwise pick the largest unit `U` such that `num_bytes >= 1024**U`, divide, and show exactly one decimal digit (always, even `.0`): `1024` -> `"1.0 KB"`, `1536` -> `"1.5 KB"`.
- Round the one-decimal value half up (toward larger magnitude on exact ties). So `1280` bytes (exactly 1.25 KB) -> `"1.3 KB"`. Do the rounding exactly, not with float `round()`.
- If rounding makes the value reach `1024.0` and a larger unit exists, move to that larger unit and show `1.0`: `1048575` -> `"1.0 MB"`.
- Raise `ValueError` if `num_bytes` is negative.

`parse_size(text: str) -> int`
- Format: a non-negative decimal number (digits with an optional fractional part like `1.5`; no sign, no exponent), optional whitespace, then a unit `B`, `KB`, `MB`, `GB`, `TB` or `PB`. Units are case-insensitive. Leading/trailing whitespace around the whole string is ignored.
- Result is the number of bytes as an `int`, with any fractional byte discarded (rounded down): `"1.5 KB"` -> `1536`, `"0.1 KB"` -> `102`, `"10mb"` -> `10485760`.
- Raise `ValueError` for anything else: empty string, missing unit, unknown unit (`"5 XB"`, `"5 K"`), missing number, negative numbers, more than one number, etc.
