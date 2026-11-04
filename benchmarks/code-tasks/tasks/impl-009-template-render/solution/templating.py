import re

_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*")
_DEFAULT = re.compile(r'default:"([^"|]*)"')
_MISSING = object()


def _lookup(path: str, context: dict):
    current = context
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, (list, tuple)) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _evaluate(expression: str, context: dict) -> str:
    parts = [p.strip() for p in expression.split("|")]
    path = parts[0]
    if not _PATH.fullmatch(path):
        raise ValueError(f"invalid variable path: {path!r}")
    value = _lookup(path, context)
    for name in parts[1:]:
        m = _DEFAULT.fullmatch(name)
        if m:
            if value is _MISSING or value is None:
                value = m.group(1)
        elif name in ("upper", "lower"):
            if value is _MISSING:
                raise KeyError(path)
            text = "" if value is None else str(value)
            value = text.upper() if name == "upper" else text.lower()
        else:
            raise ValueError(f"unknown filter: {name!r}")
    if value is _MISSING:
        raise KeyError(path)
    return "" if value is None else str(value)


def render(template: str, context: dict) -> str:
    out: list[str] = []
    pos = 0
    while True:
        start = template.find("{{", pos)
        if start == -1:
            out.append(template[pos:])
            return "".join(out)
        if start > pos and template[start - 1] == "\\":
            out.append(template[pos:start - 1])
            out.append("{{")
            pos = start + 2
            continue
        out.append(template[pos:start])
        end = template.find("}}", start + 2)
        if end == -1:
            raise ValueError("unclosed tag")
        out.append(_evaluate(template[start + 2:end], context))
        pos = end + 2
