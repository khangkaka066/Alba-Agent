Implement `diff_lines`, `render_diff` and `diff_stats` in `linediff.py`.

`diff_lines(old: list[str], new: list[str]) -> list[tuple[str, str]]` computes a minimal line diff and returns a list of `(op, line)` tuples:
- `("=", line)`: the line is present in both and is kept.
- `("-", line)`: the line exists only in `old` (removed).
- `("+", line)`: the line exists only in `new` (added).

Requirements
1. Dropping the `+` entries and reading the remaining lines in order gives exactly `old`; dropping the `-` entries gives exactly `new`.
2. The diff is minimal: the number of `=` entries equals the length of the longest common subsequence of `old` and `new` (lines compared with `==`).
3. Canonical grouping: between two consecutive `=` entries (and before the first / after the last), all `-` entries come first and then all `+` entries. A `+` is never directly followed by a `-`.
4. When several minimal diffs exist (for example `["a", "b"]` vs `["b", "a"]` can keep either line), any one that satisfies rules 1-3 is accepted. When the longest common subsequence is unique the result is fully determined.
5. Empty inputs are fine: `diff_lines([], [])` -> `[]`; `diff_lines([], ["x"])` -> `[("+", "x")]`.
6. Inputs are not modified. Lines are opaque strings (may be empty or contain spaces).

`render_diff(ops: list[tuple[str, str]]) -> str`
- Renders each entry as one line: `"  " + line` for `=`, `"- " + line` for `-`, `"+ " + line` for `+`; entries are joined with `"\n"`; no trailing newline; empty `ops` renders as `""`.
- Raise `ValueError` for an unknown op symbol.

`diff_stats(ops: list[tuple[str, str]]) -> tuple[int, int]`
- Returns `(added, removed)`: the number of `+` entries and the number of `-` entries. Raise `ValueError` for an unknown op symbol.
