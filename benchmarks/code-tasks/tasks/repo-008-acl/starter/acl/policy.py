"""Deciding whether an action is allowed."""


def matches(pattern, perm):
    """``"*"`` matches every string; a pattern ending in ``*`` (such as ``"doc:*"``) matches every string that starts with
    the text before the star; any other pattern matches only itself. A star anywhere but the last position is an
    ordinary character."""
    if pattern.endswith("*"):
        return perm.startswith(pattern[:-1])
    return pattern == perm


def can(perms, action):
    """``perms`` is an iterable of strings. A string starting with ``"!"`` is a deny rule for the pattern after the
    ``!``; every other string is an allow pattern. The action is allowed when some allow pattern matches it and no deny
    pattern matches it: a matching deny wins whatever the order of ``perms``."""
    for perm in perms:
        if perm.startswith("!"):
            if matches(perm[1:], action):
                return False
        elif matches(perm, action):
            return True
    return False
