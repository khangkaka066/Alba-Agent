_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r").strip()
        if not line or line[0] in ";#":
            continue
        if line[0] == "[":
            if not line.endswith("]") or not line[1:-1].strip():
                raise ValueError(f"line {number}: malformed section header")
            current = result.setdefault(line[1:-1].strip(), {})
            continue
        positions = [i for i in (line.find("="), line.find(":")) if i != -1]
        if not positions:
            raise ValueError(f"line {number}: expected key=value")
        sep = min(positions)
        key = line[:sep].strip()
        if not key:
            raise ValueError(f"line {number}: empty key")
        value = line[sep + 1:].strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        if current is None:
            current = result.setdefault("", {})
        current[key] = value
    return result


def get_bool(
    config: dict[str, dict[str, str]],
    section: str,
    key: str,
    default: bool | None = None,
) -> bool | None:
    value = config.get(section, {}).get(key)
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValueError(f"not a boolean: {value!r}")
