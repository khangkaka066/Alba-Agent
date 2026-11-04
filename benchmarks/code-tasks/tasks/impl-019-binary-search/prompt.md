Our reporting code repeatedly asks questions of sorted lists (timestamps, thresholds). Implement the helpers in `searching.py`. In all list-based functions `a` is a list of numbers sorted in ascending order (duplicates allowed); you do not need to validate that. None of the functions may modify `a`, and each must run in O(log n) time (not counting building any result).

- `lower_bound(a, x)`: the smallest index `i` such that `a[i] >= x`; `len(a)` if there is no such element.
- `upper_bound(a, x)`: the smallest index `i` such that `a[i] > x`; `len(a)` if there is none.
- `count_in_range(a, lo, hi)`: how many elements `v` satisfy `lo <= v <= hi` (both ends inclusive). Returns `0` if `lo > hi`.
- `nearest(a, x)`: the element of `a` closest to `x` (by absolute difference). When two elements are equally close, the smaller one is returned. Raises `ValueError` if `a` is empty.
- `first_true(pred, lo, hi)`: `pred` is a function from int to bool that is monotonic on `[lo, hi)`: it is false for some prefix of the range and true from then on. Return the smallest `n` in `[lo, hi)` for which `pred(n)` is true, or `hi` if it is never true (including when `lo >= hi`, in which case `pred` is not called at all). `pred` must be called O(log(hi - lo)) times, so it can be used on ranges of millions of values.
