Implement `to_cents`, `format_cents` and `allocate` in `money.py`. Money is handled as integer cents; no floats anywhere.

`to_cents(amount: str) -> int`
- `amount` is a decimal string: optional leading `-` or `+`, one or more digits, and optionally a `.` followed by one or more digits. Nothing else is allowed (no spaces, no thousands separators, no `.5` or `5.`, no exponent). Anything else raises `ValueError`.
- Convert to whole cents, rounding half away from zero (so `"0.005"` -> `1`, `"-0.005"` -> `-1`, `"2.675"` -> `268`, `"2.674"` -> `267`). Do the rounding exactly on the decimal digits.
- `"-0.001"` -> `0` (there is no negative zero for ints).

`format_cents(cents: int) -> str`
- Formats as `[-]D.CC` with at least one integer digit and exactly two decimals, no thousands separators: `5` -> `"0.05"`, `1999` -> `"19.99"`, `-1205` -> `"-12.05"`, `0` -> `"0.00"`.

`allocate(total_cents: int, weights: list[int]) -> list[int]`
Splits `total_cents` between the weights proportionally, using the largest-remainder method so that the shares always add up exactly to `total_cents`:
1. `share[i] = total_cents * weights[i] // sum(weights)` (floor).
2. The cents left over (`total_cents - sum(share)`) are handed out one cent each to the entries with the largest remainder `total_cents * weights[i] % sum(weights)`. Ties in remainder go to the entry with the lowest index.
- An entry with weight `0` always gets `0`.
- Returns a list of ints with the same length as `weights`.
- Raise `ValueError` if `total_cents < 0`, `weights` is empty, any weight is negative, or all weights are zero.
