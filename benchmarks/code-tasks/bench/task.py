"""Task definition and loading.

A task directory holds:
  prompt.md          what the agent is told (the only text it sees besides the starter files)
  meta.json          id, category (implement | fix), difficulty (1-3), protected files
  starter/           files copied into the agent's workspace
  hidden/            unittest files the agent never sees; used only by the grader
  solution/          reference files overlaid on the starter to prove the task is solvable
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[1] / "tasks"
CATEGORIES = ("implement", "fix")


@dataclass(frozen=True)
class Task:
    id: str
    category: str
    difficulty: int
    protected: tuple[str, ...]
    root: Path

    @property
    def prompt(self) -> str:
        return (self.root / "prompt.md").read_text(encoding="utf-8")

    @property
    def starter(self) -> Path:
        return self.root / "starter"

    @property
    def hidden(self) -> Path:
        return self.root / "hidden"

    @property
    def solution(self) -> Path:
        return self.root / "solution"


def load_task(root: Path) -> Task:
    meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
    category = meta["category"]
    if category not in CATEGORIES:
        raise ValueError(f"{root.name}: category must be one of {CATEGORIES}")
    if meta["id"] != root.name:
        raise ValueError(f"{root.name}: meta id {meta['id']!r} does not match the directory name")
    return Task(
        id=meta["id"],
        category=category,
        difficulty=int(meta["difficulty"]),
        protected=tuple(meta.get("protected", ())),
        root=root,
    )


def load_tasks(selected: set[str] | None = None) -> list[Task]:
    tasks = [load_task(p) for p in sorted(TASKS_DIR.iterdir()) if (p / "meta.json").exists()]
    return [t for t in tasks if selected is None or t.id in selected]


def file_hashes(root: Path) -> dict[str, str]:
    """Relative path -> sha256 for every regular file under ``root`` (ignoring caches)."""
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result
