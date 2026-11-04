"""Prove every task is fair before any model sees it.

For each task: (1) the untouched starter must FAIL the hidden tests, (2) the starter overlaid with the
reference solution must PASS them, (3) the solution must not change protected files, (4) the prompt must
not leak the hidden test file names. Usage: python -m bench.validate [task-id ...]
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from .grade import grade
from .task import Task, load_tasks


def _check(task: Task) -> list[str]:
    problems: list[str] = []
    for required in ("prompt.md", "meta.json"):
        if not (task.root / required).exists():
            problems.append(f"missing {required}")
    for folder in (task.starter, task.hidden, task.solution):
        if not folder.is_dir() or not any(folder.rglob("*")):
            problems.append(f"{folder.name}/ is missing or empty")
    if problems:
        return problems
    for hidden_file in task.hidden.rglob("*.py"):
        if hidden_file.name in task.prompt or hidden_file.stem in task.prompt:
            problems.append(f"prompt mentions hidden file {hidden_file.name}")
    with tempfile.TemporaryDirectory(prefix="bench-validate-") as tmp:
        starter_copy = Path(tmp) / "starter"
        shutil.copytree(task.starter, starter_copy)
        before = grade(task, starter_copy)
        if before.verdict == "PASS":
            problems.append("starter already passes the hidden tests (task is trivial)")
        solved = Path(tmp) / "solved"
        shutil.copytree(task.starter, solved)
        shutil.copytree(task.solution, solved, dirs_exist_ok=True)
        after = grade(task, solved)
        if after.verdict != "PASS":
            problems.append(f"reference solution does not pass: {after.verdict} {after.detail[-400:]}")
    return problems


def main(argv: list[str]) -> int:
    tasks = load_tasks(set(argv) or None)
    if not tasks:
        print("no tasks found")
        return 1
    bad = 0
    for task in tasks:
        problems = _check(task)
        print(f"{'OK ' if not problems else 'BAD'} {task.id} [{task.category} d{task.difficulty}]")
        for problem in problems:
            print(f"     - {problem}")
        bad += bool(problems)
    print(f"\n{len(tasks) - bad}/{len(tasks)} tasks valid")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
