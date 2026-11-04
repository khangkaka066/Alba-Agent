_PREFIX = {"=": "  ", "-": "- ", "+": "+ "}


def diff_lines(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    n, m = len(old), len(new)
    # lcs[i][j] = LCS length of old[i:] and new[j:]
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if old[i] == new[j]:
                lcs[i][j] = lcs[i + 1][j + 1] + 1
            else:
                lcs[i][j] = max(lcs[i + 1][j], lcs[i][j + 1])
    ops: list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []
    added: list[tuple[str, str]] = []
    i = j = 0
    while i < n or j < m:
        if i < n and j < m and old[i] == new[j]:
            ops.extend(removed)
            ops.extend(added)
            removed, added = [], []
            ops.append(("=", old[i]))
            i += 1
            j += 1
        elif j < m and (i == n or lcs[i][j + 1] >= lcs[i + 1][j]):
            added.append(("+", new[j]))
            j += 1
        else:
            removed.append(("-", old[i]))
            i += 1
    ops.extend(removed)
    ops.extend(added)
    return ops


def render_diff(ops: list[tuple[str, str]]) -> str:
    lines = []
    for op, line in ops:
        if op not in _PREFIX:
            raise ValueError(f"unknown op: {op!r}")
        lines.append(_PREFIX[op] + line)
    return "\n".join(lines)


def diff_stats(ops: list[tuple[str, str]]) -> tuple[int, int]:
    added = removed = 0
    for op, _ in ops:
        if op == "+":
            added += 1
        elif op == "-":
            removed += 1
        elif op != "=":
            raise ValueError(f"unknown op: {op!r}")
    return added, removed
