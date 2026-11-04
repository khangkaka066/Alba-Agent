"""Pagination helpers for list endpoints."""

DEFAULT_PER_PAGE = 20


def page_count(total_items, per_page=DEFAULT_PER_PAGE):
    """Number of pages needed to show total_items (0 items -> 0 pages)."""
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    return (total_items + per_page - 1) // per_page


def paginate(items, page, per_page=DEFAULT_PER_PAGE):
    """Return the items on a 1-based page as a new list.

    Page 1 holds the first ``per_page`` items. A page past the end returns [].
    ``page`` < 1 or ``per_page`` < 1 raises ValueError.
    """
    if page < 1:
        raise ValueError("page must be >= 1")
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    start = page * per_page
    return list(items[start:start + per_page])


def describe_page(total_items, page, per_page=DEFAULT_PER_PAGE):
    """Human readable range, e.g. 'Showing 21-40 of 95'. Empty result -> 'No results'."""
    if total_items == 0 or (page - 1) * per_page >= total_items:
        return "No results"
    first = (page - 1) * per_page + 1
    last = min(page * per_page, total_items)
    return f"Showing {first}-{last} of {total_items}"
