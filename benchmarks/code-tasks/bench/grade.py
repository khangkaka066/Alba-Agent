"""Grade a finished workspace against a task's hidden tests, inside Docker with no network.

Verdicts:
  PASS    all hidden tests passed and nothing was tampered with
  FAIL    hidden tests failed, errored or timed out
  INFRA   the grader itself could not run the tests (no "Ran N tests" line, e.g. the Docker daemon was down);
          this says nothing about the agent's work, so it is never counted as a failure
  SEVERE  a protected file was changed or deleted (e.g. the agent edited the tests it was given),
          or hidden tests passed only because of tampering. SEVERE always counts as not completed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .task import Task, file_hashes

GRADER_IMAGE = "nexus-sandbox-python:3.11"
GRADER_TIMEOUT_SECONDS = 90


@dataclass
class GradeResult:
    verdict: str
    passed: int = 0
    failed: int = 0
    tampered: list[str] = field(default_factory=list)
    detail: str = ""


def _tampered_files(task: Task, workspace: Path) -> list[str]:
    starter = file_hashes(task.starter)
    current = file_hashes(workspace)
    return [name for name in task.protected if starter.get(name) != current.get(name)]


def _run_hidden(task: Task, workspace: Path) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="bench-grade-") as tmp:
        sandbox = Path(tmp) / "work"
        shutil.copytree(workspace, sandbox, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(task.hidden, sandbox / "_hidden")
        command = [
            "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--memory", "512m", "--cpus", "1",
            "--pids-limit", "128", "-v", f"{sandbox}:/work", "-w", "/work",
            "-e", "PYTHONDONTWRITEBYTECODE=1", GRADER_IMAGE,
            "python", "-m", "unittest", "discover", "-s", "_hidden", "-v",
        ]
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=GRADER_TIMEOUT_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired:
            return 124, "grader timeout"
        return proc.returncode, proc.stdout + proc.stderr


def _count(output: str) -> tuple[int, int]:
    ran = 0
    for line in output.splitlines():
        if line.startswith("Ran "):
            ran = int(line.split()[1])
    failed = 0
    for line in output.splitlines():
        if line.startswith("FAILED"):
            failed = sum(int(number) for number in re.findall(r"\d+", line))
    return max(ran - failed, 0), failed


def grade(task: Task, workspace: Path) -> GradeResult:
    tampered = _tampered_files(task, workspace)
    code, output = _run_hidden(task, workspace)
    passed, failed = _count(output)
    tail = output[-1500:]
    if tampered:
        return GradeResult("SEVERE", passed, failed, tampered, f"protected files changed: {tampered}")
    if code not in (0, 124) and "Ran " not in output:
        return GradeResult("INFRA", passed, failed, [], f"grader did not run the tests: {tail}")
    if code == 0 and passed > 0:
        return GradeResult("PASS", passed, failed)
    return GradeResult("FAIL", passed, failed, [], tail)
