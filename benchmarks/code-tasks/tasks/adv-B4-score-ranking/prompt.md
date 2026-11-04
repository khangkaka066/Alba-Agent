Implement `ScoreError`, `rank_scores(entries)` and `top_n(entries, n)` in `ranking.py`. The starter already declares `ScoreError`; keep it.

`entries` is a list of `(name, score)` tuples; `name` is a `str`, `score` an `int` or `float`.

Validation (done for the whole list before anything else, even when the list result would be empty):
- A score outside the inclusive range `0` to `100` (so `0` and `100` are fine, `100.0001` and `-0.5` are not), or a `float` NaN, raises `ScoreError` (a subclass of `ValueError`; tests check for `ScoreError` itself).
- A `bool` score, or a score that is not an `int` or `float`, raises `TypeError`.

`rank_scores(entries)` returns a list of `(rank, name, score)` tuples, with the score unchanged from the input:
- Ordered by score, highest first. Entries with equal scores (`90` equals `90.0`) are ordered by `name` compared case-insensitively (`str.casefold()`), ascending, and if the names also match case-insensitively they keep their input order.
- Ranks use standard competition ranking ("1224"): entries with equal scores share the same rank, and the next lower score gets rank = 1 + the number of entries that have a strictly higher score. For scores 90, 80, 80, 70 the ranks are 1, 2, 2, 4.
- An empty list returns `[]`.

`top_n(entries, n)` returns the `rank_scores` tuples whose rank is `<= n`, so a tie that straddles position `n` keeps all of the tied entries and the result can be longer than `n`. `n=0` returns `[]`. A negative `n` raises `ValueError`; an `n` that is not an `int` (a `bool` counts as not an `int`) raises `TypeError`. Validation of the entries happens first, then of `n`.
