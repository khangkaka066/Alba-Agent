"""Tools that ship with the app (Node, git, ffmpeg) must be on a command's PATH, and only those: not whatever the machine has installed."""

from __future__ import annotations

import asyncio
import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from nexus_computer_sandbox import ComputerAccess, ComputerHandle
from nexus_computer_sandbox.local_provider import (
    SYSTEM_PATH, TOOLS_PATH_VARIABLE, LocalSandboxProvider, _environment, tool_directories_from_environment,
)


def test_the_path_is_interpreter_then_bundled_tools_then_system_folders(tmp_path: Path) -> None:
    tools = (tmp_path / "node" / "bin", tmp_path / "git" / "bin")
    path = _environment(tmp_path / "scratch", tmp_path / "python" / "bin", tools)["PATH"]
    assert path.split(os.pathsep) == [str(tmp_path / "python" / "bin"), *map(str, tools), *SYSTEM_PATH]


def test_without_tools_the_path_is_what_it_was(tmp_path: Path) -> None:
    path = _environment(tmp_path / "scratch", tmp_path / "python" / "bin")["PATH"]
    assert path.split(os.pathsep) == [str(tmp_path / "python" / "bin"), *SYSTEM_PATH]


def test_tool_folders_come_from_the_environment_and_relative_entries_are_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(TOOLS_PATH_VARIABLE, os.pathsep.join([str(tmp_path / "a"), "relative/bin", "", str(tmp_path / "b")]))
    assert tool_directories_from_environment() == (tmp_path / "a", tmp_path / "b")
    monkeypatch.delenv(TOOLS_PATH_VARIABLE)
    assert tool_directories_from_environment() == ()


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt exists only on macOS")
def test_a_bundled_tool_runs_by_name_and_a_host_tool_does_not(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled" / "bin"
    bundled.mkdir(parents=True)
    script = bundled / "nexus-hello"
    script.write_text("#!/bin/sh\necho hello-from-the-bundle\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    provider = LocalSandboxProvider(tmp_path / "computers", home=tmp_path / "home", tools=(bundled,))
    handle = ComputerHandle(uuid4(), ComputerAccess(uuid4(), uuid4()), "private", "local")
    handle = ComputerHandle(handle.id, handle.access, "private", "local", asyncio.run(provider.create(handle)))

    async def run(command: str) -> tuple[int, str]:
        async def sink(_stream: str, _text: str) -> None:
            return None

        done = await provider.shell(handle, command, 30, sink)
        return done.exit_code, done.stdout

    assert asyncio.run(run("nexus-hello")) == (0, "hello-from-the-bundle\n")
    # Homebrew's folder is not on the PATH, so a tool that exists only there is invisible, the same on every machine.
    code, _ = asyncio.run(run("command -v brew"))
    assert code != 0
