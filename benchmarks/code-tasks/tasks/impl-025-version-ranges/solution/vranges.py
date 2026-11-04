from __future__ import annotations

from typing import Callable, Iterable

Version = tuple[int, int, int]
Predicate = Callable[[Version], bool]


def parse_version(text: str) -> Version:
    if not isinstance(text, str):
        raise ValueError("version must be a string")
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts):
        raise ValueError(f"malformed version: {text!r}")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _clause(clause: str) -> Predicate:
    clause = clause.strip()
    if not clause:
        raise ValueError("empty clause")
    if clause == "*":
        return lambda v: True
    for op in (">=", "<=", "==", "!=", ">", "<", "=", "^", "~"):
        if clause.startswith(op):
            base = parse_version(clause[len(op):].strip())
            break
    else:
        op, base = "=", parse_version(clause)
    if op == ">=":
        return lambda v: v >= base
    if op == "<=":
        return lambda v: v <= base
    if op == ">":
        return lambda v: v > base
    if op == "<":
        return lambda v: v < base
    if op in ("=", "=="):
        return lambda v: v == base
    if op == "!=":
        return lambda v: v != base
    major, minor, patch = base
    if op == "~":
        upper = (major, minor + 1, 0)
    elif major > 0:
        upper = (major + 1, 0, 0)
    elif minor > 0:
        upper = (0, minor + 1, 0)
    else:
        upper = (0, 0, patch + 1)
    return lambda v: base <= v < upper


def _compile(spec: str) -> list[list[Predicate]]:
    if not isinstance(spec, str):
        raise ValueError("spec must be a string")
    return [[_clause(c) for c in alt.split(",")] for alt in spec.split("||")]


def _matches(alternatives: list[list[Predicate]], v: Version) -> bool:
    return any(all(p(v) for p in alt) for alt in alternatives)


def satisfies(version: str, spec: str) -> bool:
    v = parse_version(version)
    return _matches(_compile(spec), v)


def max_satisfying(versions: Iterable[str], spec: str) -> str | None:
    alternatives = _compile(spec)
    best: str | None = None
    best_v: Version | None = None
    for text in versions:
        v = parse_version(text)
        if _matches(alternatives, v) and (best_v is None or v > best_v):
            best, best_v = text, v
    return best
