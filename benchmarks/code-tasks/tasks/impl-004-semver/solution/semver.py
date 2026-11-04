import functools
import re

_IDENT = r"[0-9A-Za-z-]+"
_PATTERN = re.compile(
    rf"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    rf"(?:-({_IDENT}(?:\.{_IDENT})*))?(?:\+({_IDENT}(?:\.{_IDENT})*))?"
)


def _parse(text: str) -> tuple[tuple[int, int, int], list[str] | None]:
    m = _PATTERN.fullmatch(text)
    if m is None:
        raise ValueError(f"invalid version: {text!r}")
    pre = m.group(4).split(".") if m.group(4) is not None else None
    if pre is not None:
        for ident in pre:
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise ValueError(f"leading zero in prerelease: {text!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))), pre


def _cmp(x, y) -> int:
    return (x > y) - (x < y)


def compare_versions(a: str, b: str) -> int:
    core_a, pre_a = _parse(a)
    core_b, pre_b = _parse(b)
    if core_a != core_b:
        return _cmp(core_a, core_b)
    if pre_a is None or pre_b is None:
        return _cmp(pre_a is None, pre_b is None)
    for x, y in zip(pre_a, pre_b):
        if x == y:
            continue
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            return _cmp(int(x), int(y))
        if xn != yn:
            return -1 if xn else 1
        return _cmp(x, y)
    return _cmp(len(pre_a), len(pre_b))


def sort_versions(versions: list[str]) -> list[str]:
    for v in versions:
        _parse(v)
    return sorted(versions, key=functools.cmp_to_key(compare_versions))


def bump_version(version: str, part: str) -> str:
    (major, minor, patch), _ = _parse(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown part: {part!r}")
