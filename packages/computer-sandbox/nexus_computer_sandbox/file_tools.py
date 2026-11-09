"""Exact, atomic file edits against the virtual computer, with syntax checks and diffs."""
from __future__ import annotations

import ast
import asyncio
import difflib
import fnmatch
import json
from typing import Any
from uuid import UUID

import yaml  # type: ignore[import-untyped, unused-ignore]

from .execution_policy import Decision
from .supervisor import BoundaryGuard, ComputerAccess, ComputerSandboxSupervisor, DockerSandboxProvider

TEXT_LIMIT = 2 * 1024 * 1024


class ComputerFileTools:
    def __init__(self, supervisor: ComputerSandboxSupervisor, guard: BoundaryGuard | None = None) -> None:
        self.supervisor = supervisor
        self.guard = guard

    async def _text(self, access: ComputerAccess, computer_id: UUID, path: str) -> str:
        handle = await self.supervisor.get(access, computer_id)
        provider = self.supervisor._provider(handle.provider)
        evaluate = getattr(provider, "evaluate_command", None)
        if evaluate is not None:
            verdict = evaluate(f"cat {path!r}")
            if verdict.decision is Decision.DENY:
                raise PermissionError(verdict.reason)
        if isinstance(provider, DockerSandboxProvider):
            content = await provider.read_bounded(handle, path, TEXT_LIMIT)
        else:
            content = await self.supervisor.download(access, computer_id, path)
        if len(content) > TEXT_LIMIT:
            raise ValueError("Text operations support at most 2 MiB; use shell tools for larger binary data")
        return content.decode("utf-8")

    async def view_file_numbered(self, access: ComputerAccess, computer_id: UUID, path: str, start_line: int = 1, end_line: int = 200) -> dict[str, Any]:
        if start_line < 1 or end_line < start_line or end_line - start_line > 1000:
            raise ValueError("Use a 1-indexed range of at most 1001 lines")
        text = await self._text(access, computer_id, path)
        lines = text.splitlines()
        return {"path": path, "total_lines": len(lines), "content": "\n".join(f"{number}: {lines[number - 1]}" for number in range(start_line, min(end_line, len(lines)) + 1))}

    async def surgical_file_edit(self, access: ComputerAccess, computer_id: UUID, path: str, old_text: str, new_text: str) -> dict[str, Any]:
        if not old_text:
            raise ValueError("old_text must identify a non-empty, unique block")
        before = await self._text(access, computer_id, path)
        count = before.count(old_text)
        if count != 1:
            raise ValueError(f"Exact edit requires one match; found {count}")
        after = before.replace(old_text, new_text, 1)
        if len(after.encode()) > TEXT_LIMIT:
            raise ValueError("Edited text exceeds 2 MiB")
        if path.endswith(".py"):
            ast.parse(after, filename=path)
        elif path.endswith(".json"):
            json.loads(after)
        elif path.endswith((".yml", ".yaml")):
            yaml.safe_load(after)
        handle = await self.supervisor.get(access, computer_id)
        provider = self.supervisor._provider(handle.provider)
        if not isinstance(provider, DockerSandboxProvider):
            raise ValueError("Atomic file editing is unavailable for this provider")
        evaluate = getattr(provider, "evaluate_command", None)
        if evaluate is not None:
            verdict = evaluate(f"edit {path!r}")
            if verdict.decision is Decision.DENY:
                raise PermissionError(verdict.reason)
            if verdict.decision is Decision.ASK:
                guard = self.guard or self.supervisor._boundary_guard
                if guard is None:
                    raise PermissionError("File editing requires approval under the current execution policy")
                await guard(access, "external_action", f"Edit {path}")
        snapshot = await asyncio.to_thread(provider.snapshots(handle).create)
        # A concurrent edit must fail rather than overwrite text the caller never saw.
        current = await self._text(access, computer_id, path)
        if current != before:
            raise ValueError("File changed during review; read it again before editing")
        await provider.atomic_text(handle, path, after.encode())
        diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}"))
        await self.supervisor._audit(access, computer_id, "computer.file_edited", {"path": path, "snapshot_id": str(snapshot["id"])})
        return {"path": path, "diff": diff, "before": before, "after": after, "snapshot_id": snapshot["id"], "syntax_checked": path.endswith((".py", ".json", ".yml", ".yaml"))}

    async def fast_workspace_search(self, access: ComputerAccess, computer_id: UUID, pattern: str, path_glob: str = "*") -> dict[str, Any]:
        if not pattern or len(pattern) > 500:
            raise ValueError("Search pattern must contain 1–500 characters")
        # Literal search is deterministic and cannot expose the server to pathological regular expressions.
        handle = await self.supervisor.get(access, computer_id)
        provider = self.supervisor._provider(handle.provider)
        hits: list[dict[str, Any]] = []
        scanned = 0
        for path in await provider.files(handle):
            if not fnmatch.fnmatchcase(path, path_glob):
                continue
            try:
                text = await self._text(access, computer_id, path)
            except (UnicodeError, ValueError, PermissionError):
                continue
            scanned += 1
            for number, line in enumerate(text.splitlines(), 1):
                if pattern in line:
                    hits.append({"path": path, "line": number, "text": line[:2000]})
                    if len(hits) >= 200:
                        return {"matches": hits, "truncated": True, "files_scanned": scanned}
            if scanned >= 2000:
                break
        return {"matches": hits, "truncated": scanned >= 2000, "files_scanned": scanned}
