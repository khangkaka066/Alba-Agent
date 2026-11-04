We store long, repetitive status strings compactly with a hand-rolled run-length format. Implement `runs`, `encode` and `decode` in `rle.py`.

**Format.** The encoded form is a sequence of runs, each written as `<count><char>`: `count` is a decimal integer >= 1 without leading zeros and `char` is the repeated character. For example `"aaabcc"` encodes to `"3a1b2c"`. Because counts are decimal, a `char` that is a digit (`0`-`9`) or a backslash is written with a backslash in front of it: `"111"` encodes to `"3\1"` (that is: `3`, backslash, `1`) and a single backslash encodes to `1\\` (`1`, backslash, backslash). Every other character (spaces, newlines, unicode, ...) is written as is.

**`runs(text) -> list[tuple[str, int]]`**: the maximal runs of identical consecutive characters as `(char, count)` pairs, in order. `runs("aab") == [("a", 2), ("b", 1)]`; the empty string gives `[]`.

**`encode(text) -> str`**: encodes `text` using maximal runs, so adjacent runs never use the same character. The empty string encodes to `""`. Runs may be arbitrarily long (`"a" * 1000` is `"1000a"`).

**`decode(data, max_length=None) -> str`**: the inverse of `encode`. It must also accept non-canonical input such as `"1a1a"` (which decodes to `"aa"`). It raises `ValueError` for malformed input:
- a run that does not start with a count (e.g. `"a3b"`, or a leading backslash);
- a count with a leading zero or a count of `0` (`"01a"`, `"0a"`);
- a count with no character after it (`"3"`, `"3a2"`);
- a backslash that is not followed by a digit or a backslash (`"1\a"`, or a trailing backslash).

`decode("")` is `""`. If `max_length` is not `None` and the total decoded length would exceed it, `ValueError` is raised; this check must happen **before** the output is built, so a hostile input such as `"999999999999a"` is rejected without allocating memory (a decoded length equal to `max_length` is allowed; only a longer one is rejected). Malformed input still raises `ValueError` when `max_length` is given.

For every string `s`, `decode(encode(s)) == s`.
