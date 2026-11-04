from __future__ import annotations

from typing import Any


class PathSyntaxError(ValueError):
    pass


_BARE_STOP = '.[]"'
_MISSING = object()


def parse_path(path: str) -> list[str | int]:
    steps: list[str | int] = []
    i, n = 0, len(path)
    while i < n:
        ch = path[i]
        if ch == "[":
            i += 1
            if i < n and path[i] == '"':
                i += 1
                chars: list[str] = []
                while True:
                    if i >= n:
                        raise PathSyntaxError("unterminated quoted key")
                    c = path[i]
                    if c == "\\":
                        if i + 1 >= n or path[i + 1] not in '"\\':
                            raise PathSyntaxError("bad escape")
                        chars.append(path[i + 1])
                        i += 2
                    elif c == '"':
                        i += 1
                        break
                    else:
                        chars.append(c)
                        i += 1
                if i >= n or path[i] != "]":
                    raise PathSyntaxError("expected ]")
                i += 1
                steps.append("".join(chars))
            else:
                end = path.find("]", i)
                if end < 0:
                    raise PathSyntaxError("unclosed [")
                body = path[i:end]
                digits = body[1:] if body.startswith("-") else body
                if not digits or not (digits.isascii() and digits.isdigit()):
                    raise PathSyntaxError("bad index")
                steps.append(int(body))
                i = end + 1
        else:
            if ch == ".":
                if not steps and i == 0:
                    raise PathSyntaxError("leading dot")
                i += 1
                if i >= n or path[i] in _BARE_STOP:
                    raise PathSyntaxError("expected key after dot")
            elif steps:
                raise PathSyntaxError("expected . or [")
            elif ch in _BARE_STOP:
                raise PathSyntaxError("unexpected character")
            j = i
            while j < n and path[j] not in _BARE_STOP:
                j += 1
            steps.append(path[i:j])
            i = j
            continue
        if i < n and path[i] not in ".[":
            raise PathSyntaxError("expected . or [")
    return steps


def _follow(data: Any, path: str) -> Any:
    current = data
    for step in parse_path(path):
        if isinstance(step, int):
            if not isinstance(current, list) or not -len(current) <= step < len(current):
                return _MISSING
            current = current[step]
        else:
            if not isinstance(current, dict) or step not in current:
                return _MISSING
            current = current[step]
    return current


def get_path(data: Any, path: str, default: Any = None) -> Any:
    result = _follow(data, path)
    return default if result is _MISSING else result


def has_path(data: Any, path: str) -> bool:
    return _follow(data, path) is not _MISSING
