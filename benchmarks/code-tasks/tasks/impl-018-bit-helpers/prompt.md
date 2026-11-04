Our binary-protocol code needs a handful of bit manipulation helpers. Implement the functions in `bits.py`. All integer arguments are Python `int`s; bit index 0 is the least significant bit.

Unless stated otherwise, `n` must be >= 0 and every bit index/width/length argument must be >= 0, otherwise `ValueError` is raised (check this before doing anything else).

- `popcount(n)`: number of 1 bits in `n`. `popcount(0) == 0`.
- `is_power_of_two(n)`: `True` iff `n` is 1, 2, 4, 8, ... For `0` and for negative numbers it returns `False` (it never raises).
- `next_power_of_two(n)`: the smallest power of two that is >= `n`. Both `0` and `1` give `1`. Negative `n` raises `ValueError`.
- `get_bit(n, i)`: the bit at index `i` as `0` or `1`.
- `set_bit(n, i)`, `clear_bit(n, i)`, `toggle_bit(n, i)`: return `n` with bit `i` set to 1 / set to 0 / flipped.
- `extract_bits(n, start, length)`: the `length` bits of `n` beginning at index `start`, as an int (bit `start` becomes bit 0 of the result). `length == 0` gives `0`. Bits above the top of `n` read as 0.
- `reverse_bits(n, width)`: reverse the order of the lowest `width` bits of `n`. `width` must be >= 1 and `n` must fit in `width` bits (`n < 2**width`), otherwise `ValueError`. Example: `reverse_bits(0b0011, 4) == 0b1100`, and `reverse_bits(1, 8) == 128`.
- `lowest_set_bit(n)`: the value of the lowest 1 bit of `n` (e.g. `12 -> 4`), `0` for `0`.
