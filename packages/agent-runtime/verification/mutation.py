"""Stdlib-only AST mutation and self-test gates; also embedded verbatim into the sandbox probe.

Do not add imports outside the standard library or relative imports: the file is concatenated into a script
that runs inside the container.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

_COMPARE = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
_BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}
_BOOLOP = {ast.And: ast.Or, ast.Or: ast.And}


class _Mutator(ast.NodeTransformer):
    """Applies exactly one mutation, the `target`-th mutation site in a deterministic walk; `target < 0` only counts."""

    def __init__(self, target: int) -> None:
        self.target = target
        self.sites = 0

    def _hit(self) -> bool:
        index = self.sites
        self.sites += 1
        return index == self.target

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        for position, operator in enumerate(node.ops):
            if type(operator) in _COMPARE and self._hit():
                node.ops[position] = _COMPARE[type(operator)]()
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if type(node.op) in _BINOP and self._hit():
            node.op = _BINOP[type(node.op)]()
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if type(node.op) in _BOOLOP and self._hit():
            node.op = _BOOLOP[type(node.op)]()
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit():
            return node.operand
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            if self._hit():
                return ast.copy_location(ast.Constant(value=not node.value), node)
        elif isinstance(node.value, int):
            if self._hit():
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST:
        self.generic_visit(node)
        if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None) and self._hit():
            node.value = ast.Constant(value=None)
        return node


def count_sites(source: str) -> int:
    mutator = _Mutator(-1)
    mutator.visit(ast.parse(source))
    return mutator.sites


def mutate(source: str, site: int) -> str:
    tree = ast.parse(source)
    mutator = _Mutator(site)
    tree = mutator.visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def pick_sites(total: int, limit: int) -> list[int]:
    """Spread at most `limit` sites evenly over `total` so one long module cannot hog the budget."""
    if total <= limit:
        return list(range(total))
    return sorted({int(index * total / limit) for index in range(limit)})


def run_tests(directory: str, test_files: list[str], timeout: int) -> tuple[int, bool]:
    """Run test files in `directory`; return `(tests_ran, all_passed)`. A timeout counts as failure."""
    modules = [name[:-3] for name in test_files]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        done = subprocess.run(
            [sys.executable, "-m", "unittest", *modules], cwd=directory, env=environment,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return 0, False
    match = re.search(r"Ran (\d+) tests?", done.stderr)
    return (int(match.group(1)) if match else 0), done.returncode == 0


def gate(
    workspace: str, source_files: list[str], test_files: list[str], baseline: dict[str, bytes],
    *, mutants_per_file: int = 12, timeout: int = 15,
) -> dict[str, object]:
    """Self-test gates: tests pass on the code, fail on the starting code, and fail on most mutants of the code."""
    ran, passed = run_tests(workspace, test_files, timeout)
    result: dict[str, object] = {"ran": ran, "passed": passed, "discriminates": False, "mutants": 0, "killed": 0}
    if not passed or ran == 0:
        return result
    with tempfile.TemporaryDirectory(prefix="nexus-gate-") as scratch:
        shutil.copytree(workspace, scratch, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "attempt_*"))
        for name in source_files:
            target = os.path.join(scratch, name)
            if name in baseline:
                with open(target, "wb") as handle:
                    handle.write(baseline[name])
            elif os.path.exists(target):
                os.remove(target)
        _, baseline_passed = run_tests(scratch, test_files, timeout)
        result["discriminates"] = not baseline_passed
        for name in source_files:
            with open(os.path.join(workspace, name), encoding="utf-8") as handle:
                original = handle.read()
            try:
                total = count_sites(original)
            except SyntaxError:
                continue
            for site in pick_sites(total, mutants_per_file):
                shutil.copy(os.path.join(workspace, name), os.path.join(scratch, name))
                with open(os.path.join(scratch, name), "w", encoding="utf-8") as handle:
                    handle.write(mutate(original, site))
                _, mutant_passed = run_tests(scratch, test_files, timeout)
                result["mutants"] = int(result["mutants"]) + 1  # type: ignore[call-overload]
                if not mutant_passed:
                    result["killed"] = int(result["killed"]) + 1  # type: ignore[call-overload]
            shutil.copy(os.path.join(workspace, name), os.path.join(scratch, name))
    return result
