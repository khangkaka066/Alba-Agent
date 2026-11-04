Implement `page_window` and `page_bounds` in `pager.py`.

`page_window(current: int, total: int, siblings: int = 1, edges: int = 1) -> list[int | str]`
builds the list of page links to display, as in a pagination bar. Pages are numbered from 1.
1. The pages to show are: the first `edges` pages, the last `edges` pages, and every page within `siblings` of `current` on either side (`current - siblings .. current + siblings`), all clipped to the range `1..total`.
2. Sort them ascending without duplicates.
3. Walk through consecutive shown pages `p` and `q` (with `q > p + 1`): if exactly one page is missing between them (`q == p + 2`), include that page; if two or more are missing, put the string `"..."` between them.
4. Return the resulting list of ints and `"..."` markers.
- Examples: `page_window(5, 10)` -> `[1, "...", 4, 5, 6, "...", 10]`; `page_window(4, 7)` -> `[1, 2, 3, 4, 5, 6, 7]`; `page_window(1, 10)` -> `[1, 2, "...", 10]`; `page_window(1, 1)` -> `[1]`; `page_window(8, 20, siblings=0, edges=2)` -> `[1, 2, "...", 8, "...", 19, 20]`.
- Raise `ValueError` if `total < 1`, if `current` is not within `1..total`, or if `siblings < 0` or `edges < 0`.
- `edges=0` means no page is forced at the ends, so only the pages around `current` are shown and no marker is added before the first or after the last shown page (markers only ever go between two shown pages): `page_window(10, 20, edges=0)` -> `[9, 10, 11]`; `page_window(1, 20, edges=0)` -> `[1, 2]`.

`page_bounds(page: int, per_page: int, total_items: int) -> tuple[int, int]`
- Returns `(start, end)` slice indices for a 1-based `page`: `start = (page - 1) * per_page`, `end = min(start + per_page, total_items)`. If `start` is beyond the items, return `(total_items, total_items)` (an empty slice).
- Raise `ValueError` if `page < 1`, `per_page < 1` or `total_items < 0`.
- Examples: `page_bounds(1, 10, 25)` -> `(0, 10)`; `page_bounds(3, 10, 25)` -> `(20, 25)`; `page_bounds(9, 10, 25)` -> `(25, 25)`; `page_bounds(1, 10, 0)` -> `(0, 0)`.
