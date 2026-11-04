def page_window(current: int, total: int, siblings: int = 1, edges: int = 1) -> list[int | str]:
    raise NotImplementedError


def page_bounds(page: int, per_page: int, total_items: int) -> tuple[int, int]:
    raise NotImplementedError
