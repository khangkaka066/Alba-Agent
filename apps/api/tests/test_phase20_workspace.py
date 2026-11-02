"""Plain requests still deliver files: sandbox output without a declared contract is exported."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from flows.compiler import FlowCompiler


def test_undeclared_sandbox_files_become_deliverables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    files = {"report.md": b"# Report", "src/data.csv": b"a,b\n1,2", "workspace_manifest.json": b"{}", "auth.py": b"unchanged", "edited.py": b"new version"}

    async def reader(_tenant: Any, _workspace: Any, _run: Any, path: str) -> bytes:
        return files[path]

    compiler = object.__new__(FlowCompiler)
    cast(Any, compiler)._sandbox_file_reader = reader
    state = SimpleNamespace(tenant_id=uuid4(), workspace_id=uuid4(), run_id=uuid4())
    inputs = {"auth.py": b"unchanged", "edited.py": b"old version"}
    produced = ("./report.md", "src/data.csv", "workspace_manifest.json", "auth.py", "edited.py", "__pycache__/x.pyc", "../escape.txt")
    delivered = asyncio.run(cast(Any, compiler)._export_undeclared(state, inputs, produced))
    assert sorted(delivered) == ["edited.py", "report.md", "src/data.csv"]  # inputs left unchanged and the manifest are not deliverables
    run_dir = tmp_path / str(state.tenant_id) / str(state.workspace_id) / str(state.run_id)
    assert (run_dir / "report.md").read_bytes() == b"# Report" and (run_dir / "src" / "data.csv").is_file()
    assert (run_dir / "edited.py").read_bytes() == b"new version"
    assert not (run_dir.parent / "escape.txt").exists()
