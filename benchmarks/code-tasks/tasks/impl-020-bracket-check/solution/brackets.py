from __future__ import annotations

_PAIRS = {")": "(", "]": "[", "}": "{"}
_OPENERS = set(_PAIRS.values())


def find_bracket_error(text: str) -> tuple[str, int] | None:
    stack: list[tuple[str, int]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            start = i
            i += 1
            while True:
                if i >= n or text[i] == "\n":
                    return ("unterminated_string", start)
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == ch:
                    break
                i += 1
        elif ch == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif ch in _OPENERS:
            stack.append((ch, i))
        elif ch in _PAIRS:
            if not stack:
                return ("unexpected_closer", i)
            if stack[-1][0] != _PAIRS[ch]:
                return ("mismatched", i)
            stack.pop()
        i += 1
    if stack:
        return ("unclosed", stack[-1][1])
    return None


def is_balanced(text: str) -> bool:
    return find_bracket_error(text) is None
