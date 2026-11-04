def page_window(current: int, total: int, siblings: int = 1, edges: int = 1) -> list[int | str]:
    if total < 1:
        raise ValueError("total must be >= 1")
    if not 1 <= current <= total:
        raise ValueError("current out of range")
    if siblings < 0 or edges < 0:
        raise ValueError("siblings and edges must be >= 0")
    shown = set(range(1, min(edges, total) + 1))
    shown.update(range(max(total - edges + 1, 1), total + 1))
    shown.update(range(max(current - siblings, 1), min(current + siblings, total) + 1))
    result: list[int | str] = []
    previous = 0
    for page in sorted(shown):
        gap = page - previous - 1
        if previous and gap == 1:
            result.append(previous + 1)
        elif previous and gap > 1:
            result.append("...")
        result.append(page)
        previous = page
    return result


def page_bounds(page: int, per_page: int, total_items: int) -> tuple[int, int]:
    if page < 1 or per_page < 1 or total_items < 0:
        raise ValueError("invalid pagination arguments")
    start = (page - 1) * per_page
    if start >= total_items:
        return (total_items, total_items)
    return (start, min(start + per_page, total_items))
