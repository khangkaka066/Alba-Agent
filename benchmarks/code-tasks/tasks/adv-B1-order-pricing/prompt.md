Implement `price_order(items, tax_percent, coupon_percent=None)` in `pricing.py`. All money is exact decimal arithmetic (use `decimal.Decimal`, never `float`) and every amount is rounded to whole cents with banker's rounding (round half to even: `0.125 -> 0.12`, `0.135 -> 0.14`).

Inputs:
- `items`: a list of `(unit_price, qty)` tuples. `unit_price` is a string such as `"2.675"` (any number of decimal places, not negative). `qty` is an `int` of at least 1; a `bool` is not a valid quantity.
- `tax_percent`: a string such as `"5"` or `"8.25"`, between 0 and 100 inclusive.
- `coupon_percent`: `None` means no coupon. Otherwise a string between 0 and 100 inclusive, such as `"10"`. A coupon of `"0"` is a valid coupon that happens to discount nothing; an empty string `""` is invalid.

Calculation, done line by line (each line is rounded on its own, and the totals are the sums of the rounded line values):
1. `line = round(unit_price * qty)`.
2. `discount = round(line * coupon_percent / 100)` (zero when there is no coupon).
3. `tax = round((line - discount) * tax_percent / 100)`.

Return a dict with the keys `"subtotal"` (sum of lines), `"discount"` (sum of discounts), `"tax"` (sum of taxes) and `"total"` (`subtotal - discount + tax`). Every value is a string with exactly two decimal places, e.g. `"12.30"`. An empty `items` list is valid and gives `"0.00"` everywhere.

Errors: any invalid input (bad price string, negative price, bad quantity, tax or coupon outside the range or not parseable, empty-string coupon) raises `ValueError`. Passing `None` as `items` or as `tax_percent` raises `TypeError`.
