"""Sandbox input staging rejects path traversal before invoking Docker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest

from nexus_computer_sandbox import DockerSandboxSupervisor


@pytest.mark.parametrize("filename", ["../escape.csv", "/tmp/escape.csv", "data/../../escape.csv", "data//escape.csv", "attempt_control.py"])
def test_sandbox_rejects_escaping_input_name_without_creating_external_files(filename: str) -> None:
    async def check(root: Path) -> None:
        runner = DockerSandboxSupervisor(root)

        async def sink(_stream: str, _content: str) -> None:
            return None

        with pytest.raises(ValueError, match="relative workspace paths"):
            await runner.run_python(
                uuid4(), uuid4(), uuid4(), "print('never run')", "true", 1, 5, sink,
                input_files={filename: b"unsafe"},
            )
        assert not (root.parent / "escape.csv").exists()

    with TemporaryDirectory(prefix="nexus-input-test-") as directory:
        asyncio.run(check(Path(directory)))
