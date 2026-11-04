Implement `merge_intervals` and `covered_points` in `intervals.py`.

Intervals are closed integer ranges given as `(start, end)` tuples, meaning every integer `x` with `start <= x <= end`.

`merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]`
- Returns the minimal list of disjoint intervals covering the same points, sorted by start ascending.
- Two intervals are merged when they overlap or share at least one point (so `(1, 3)` and `(3, 5)` become `(1, 5)`). Intervals that merely sit next to each other without sharing a point, such as `(1, 2)` and `(3, 4)`, are NOT merged.
- An interval fully inside another disappears into it. Duplicates collapse.
- The input may be in any order and is not modified. An empty input returns `[]`.
- Each interval must satisfy `start <= end`; otherwise raise `ValueError` (even if the bad interval would have been swallowed by another one). A single-point interval like `(4, 4)` is valid.
- The returned items are plain `tuple`s.

`covered_points(intervals: list[tuple[int, int]]) -> int`
- Number of distinct integers covered by the union of the intervals (`[(1, 3), (3, 5)]` -> `5`, `[(1, 2), (3, 4)]` -> `4`). Empty input -> `0`. Same validation as above.
