def diff_lines(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    raise NotImplementedError


def render_diff(ops: list[tuple[str, str]]) -> str:
    raise NotImplementedError


def diff_stats(ops: list[tuple[str, str]]) -> tuple[int, int]:
    raise NotImplementedError
