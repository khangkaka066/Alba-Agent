"""Static scan for names a module reads but never defines anywhere.

Passing tests prove only the lines they run: a branch the shipped tests never reach can still raise NameError. This scan
is deliberately conservative so that it rarely blames correct code: a name bound anywhere in the file (an import, a
definition, an assignment, a parameter, a comprehension or `except ... as` target, a `global` declaration) counts as
defined in every scope. It therefore misses scope mistakes but catches the common one: a name that is used and never
imported or defined at all. A file with `from x import *` is skipped because its names cannot be known.

The module is stdlib only and has no relative imports, so the probe can paste its source into the script it runs in the
sandbox, next to the evidence it reports.
"""

import ast
import builtins
import os
import re

_TEST_FILE = re.compile(r"^(test_[A-Za-z0-9_]*|[A-Za-z0-9_]*_test)\.py$")
_MODULE_NAMES = frozenset({
    "__name__", "__file__", "__doc__", "__spec__", "__package__", "__loader__", "__builtins__", "__path__",
    "__annotations__", "__class__", "__debug__", "__cached__",
})
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "upstream", "_hidden"})
_MAX_BYTES = 400_000
_MAX_REPORTED = 8


def _bound_names(tree: ast.AST) -> set[str] | None:
    """Every name bound anywhere in the tree, or None when a star import makes that unknowable."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    return None
                names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            for param in getattr(node, "type_params", ()) or ():
                names.add(param.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif type(node).__name__ in ("MatchAs", "MatchStar"):
            captured = getattr(node, "name", None)
            if captured:
                names.add(str(captured))
        elif type(node).__name__ == "MatchMapping":
            rest = getattr(node, "rest", None)
            if rest:
                names.add(str(rest))
        elif type(node).__name__ == "TypeAlias":
            names.add(str(getattr(getattr(node, "name", None), "id", "")))
    return names


def undefined_names(source: str, filename: str = "<module>") -> list[str]:
    """`file:line name` for each name that is read but bound nowhere in the file; a file that does not parse reports none."""
    try:
        tree = ast.parse(source, filename)
    except (SyntaxError, ValueError, RecursionError):
        return []
    bound = _bound_names(tree)
    if bound is None:
        return []
    known = bound | _MODULE_NAMES | set(dir(builtins))
    found: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in known:
            if node.id not in seen:
                seen.add(node.id)
                found.append(f"{filename}:{node.lineno} {node.id}")
    return sorted(found, key=lambda item: (item.split(":")[0], int(item.split(":")[1].split(" ")[0])))


def scan_undefined(root: str) -> list[str]:
    """Scan the program files under `root`; tests, the coder's attempt scripts and hidden folders are left out."""
    findings: list[str] = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in _SKIP_DIRS and not name.startswith("."))
        for name in sorted(files):
            if not name.endswith(".py") or _TEST_FILE.match(name) or name.startswith("attempt_"):
                continue
            path = os.path.join(folder, name)
            try:
                if os.path.getsize(path) > _MAX_BYTES:
                    continue
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
            except (OSError, UnicodeDecodeError):
                continue
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            findings.extend(undefined_names(source, relative))
            if len(findings) >= _MAX_REPORTED:
                return findings[:_MAX_REPORTED]
    return findings
