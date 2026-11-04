Implement `merge_tags(lists, limit=None)` in `tags.py`. It merges several lists of user-entered tags into one ranked list of distinct tags.

- `lists` is a list of lists of `str`. A non-`str` tag raises `TypeError`.
- Each tag is stripped of leading and trailing whitespace first (inner whitespace is untouched). A tag that is empty after stripping is ignored.
- Two tags are the same tag when their comparison keys are equal. The key is: Unicode NFC normalisation (`unicodedata.normalize("NFC", ...)`) of the stripped tag, then `str.casefold()`. So `"Python"` and `"PYTHON"` are the same tag, `"Straße"` and `"STRASSE"` are the same tag, and a composed `"é"` equals a decomposed `"é"`.
- The tag's count is the number of times it occurs across all lists, counting repeats inside one list too.
- The output spelling of a tag is its first occurrence (scanning the lists in order, each list left to right), stripped but otherwise exactly as typed (no case change, no normalisation).
- The output is ordered by count, highest first. Tags with equal counts stay in the order of their first occurrence (not alphabetical).
- `limit=None` returns every tag. Otherwise return only the first `limit` tags of the ordered output, so `limit=0` returns `[]`. A negative `limit` raises `ValueError`; a `limit` that is not an `int` (a `bool` counts as not an `int`) raises `TypeError`.
- `lists=[]` or all-empty lists return `[]`.
- The input lists must not be modified.
