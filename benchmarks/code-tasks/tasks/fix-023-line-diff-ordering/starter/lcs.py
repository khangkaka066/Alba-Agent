"""Longest-common-subsequence table for line diffs."""


def lcs_table(a, b):
    """Return ``t`` where ``t[i][j]`` is the LCS length of ``a[i:]`` and ``b[j:]``.

    The table has ``len(a) + 1`` rows and ``len(b) + 1`` columns; the last row and
    last column are zeros.
    """
    t = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            if a[i] == b[j]:
                t[i][j] = t[i + 1][j + 1] + 1
            else:
                t[i][j] = max(t[i + 1][j], t[i][j + 1])
    return t
