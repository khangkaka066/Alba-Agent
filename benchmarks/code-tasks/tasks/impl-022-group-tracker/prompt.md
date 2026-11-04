We merge duplicate customer records: every time two records are found to describe the same person we link them, and we need to ask which records belong together. Implement the `GroupTracker` class in `groups.py` (elements are hashable and mutually orderable, e.g. ints or strings).

- `add(x)`: registers `x` as a singleton group if it is not known yet; does nothing otherwise.
- `union(a, b) -> bool`: merges the groups of `a` and `b`; elements not seen before are registered automatically. Returns `True` if two different groups were merged, `False` if they were already in the same group (including `union(a, a)`).
- `connected(a, b) -> bool`: whether both are in the same group. Raises `KeyError` if either element is unknown.
- `size_of(x) -> int`: the size of `x`'s group. Raises `KeyError` if `x` is unknown.
- `members(x) -> list`: the members of `x`'s group sorted ascending. Raises `KeyError` if `x` is unknown.
- `group_count`: read-only property, the current number of groups.
- `groups() -> list[list]`: every group as a sorted list, with the groups themselves ordered by their smallest element, ascending. Empty tracker gives `[]`.
- `len(tracker)` is the number of known elements; `x in tracker` tells whether `x` is known.

The structure must stay fast and must not hit the recursion limit when groups contain tens of thousands of elements joined in long chains (for example `union(0, 1)`, `union(1, 2)`, ..., `union(99999, 100000)`): use an iterative union-find (path compression and/or union by size), not recursion.
