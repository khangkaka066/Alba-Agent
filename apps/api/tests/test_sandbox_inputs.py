"""Sandbox input staging rejects path traversal before invoking Docker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from nexus_computer_sandbox import DockerSandboxSupervisor


def test_sandbox_rejects_pathful_input_name_without_creating_external_files() -> None:
    async def check(root: Path) -> None:
        runner = DockerSandboxSupervisor(root)

        async def sink(_stream: str, _content: str) -> None:
            return None

        with pytest.raises(ValueError, match="simple workspace names"):
            await runner.run_python(
                uuid4(), uuid4(), uuid4(), "print('never run')", "true", 1, 5, sink,
                input_files={"../escape.csv": b"unsafe"},
            )
        assert not (root.parent / "escape.csv").exists()

    with TemporaryDirectory(prefix="nexus-input-test-") as directory:
        asyncio.run(check(Path(directory)))
