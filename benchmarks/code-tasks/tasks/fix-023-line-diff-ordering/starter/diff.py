"""Line-based diff built on the LCS table."""

from lcs import lcs_table


def diff_lines(a, b):
    """Return a list of ``(op, line)`` pairs turning list ``a`` into list ``b``.

    ``op`` is ``"="`` (line kept), ``"-"`` (line only in ``a``) or ``"+"`` (line only in
    ``b``). The kept lines form a longest common subsequence of the two inputs. Inside
    a run of changes between two kept lines, all deletions come first and then all
    insertions, each in the original line order.
    """
    t = lcs_table(a, b)
    ops = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            ops.append(("=", a[i]))
            i += 1
            j += 1
        elif t[i + 1][j] > t[i][j + 1]:
            ops.append(("-", a[i]))
            i += 1
        else:
            ops.append(("+", b[j]))
            j += 1
    ops.extend(("-", line) for line in a[i:])
    ops.extend(("+", line) for line in b[j:])
    return ops
