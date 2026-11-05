"""The programs the desktop installer ships for agent commands work from inside the sandbox, found by name, with nothing from the builder.

Needs a runtime built by scripts/package/build_runtime.py for this Mac's CPU; without one the tests are skipped (a CI machine that only runs
the API tests has none). `scripts/package/verify_runtime.py` is the broader audit; this proves the same tools run the way an agent runs them.
"""

from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from nexus_computer_sandbox import ComputerAccess, ComputerHandle
from nexus_computer_sandbox.local_provider import LocalSandboxProvider

RUNTIME = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "runtime" / ("mac-arm64" if platform.machine() == "arm64" else "mac-x64")

pytestmark = [
    pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt exists only on macOS"),
    pytest.mark.skipif(not (RUNTIME / "node" / "bin" / "node").exists(), reason="no desktop runtime built for this CPU"),
]


class Sandbox:
    def __init__(self, root: Path) -> None:
        tools = tuple(path for path in (RUNTIME / "node" / "bin", RUNTIME / "git" / "bin", RUNTIME / "tools" / "bin") if path.exists())
        self.provider = LocalSandboxProvider(root / "computers", home=root / "home", interpreter=RUNTIME / "python" / "bin" / "python3", tools=tools)
        access = ComputerAccess(uuid4(), uuid4())
        handle = ComputerHandle(uuid4(), access, "private", "local")
        self.handle = ComputerHandle(handle.id, access, "private", "local", asyncio.run(self.provider.create(handle)))

    def run(self, command: str) -> tuple[int, str, str]:
        async def sink(_stream: str, _text: str) -> None:
            return None

        done = asyncio.run(self.provider.shell(self.handle, command, 120, sink))
        return done.exit_code, done.stdout.strip(), done.stderr.strip()


@pytest.fixture()
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


def test_node_and_npm_run_by_name(sandbox: Sandbox) -> None:
    assert sandbox.run("node -e 'console.log(6 * 7)'")[:2] == (0, "42")
    code, out, err = sandbox.run("npm --version")
    assert code == 0 and out[0].isdigit(), err


def test_git_commits_and_finds_its_helpers_inside_the_bundle(sandbox: Sandbox) -> None:
    code, out, err = sandbox.run("git init -q repo && cd repo && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m first && git log --oneline")
    assert code == 0 and out.endswith("first"), err
    assert sandbox.run("git --exec-path")[1].startswith(str(RUNTIME / "git"))


def test_console_scripts_start_without_the_builders_path(sandbox: Sandbox) -> None:
    for command in ("pytest --version", "alembic --version", "uvicorn --version"):
        code, out, err = sandbox.run(command)
        assert code == 0, f"{command}: {err or out}"


@pytest.mark.skipif(not (RUNTIME / "tools" / "bin" / "ffmpeg").exists(), reason="this runtime has no ffmpeg")
def test_ffmpeg_makes_h264_and_aac(sandbox: Sandbox) -> None:
    code, out, err = sandbox.run("ffmpeg -v error -f lavfi -i testsrc=duration=1:size=128x128:rate=10 -c:v h264_videotoolbox -y v.mp4 && ffprobe -v error -show_entries stream=codec_name -of csv=p=0 v.mp4")
    assert code == 0 and out == "h264", err
    code, out, err = sandbox.run("ffmpeg -v error -f lavfi -i sine=duration=1 -c:a aac -y a.m4a && ffprobe -v error -show_entries stream=codec_name -of csv=p=0 a.m4a")
    assert code == 0 and out == "aac", err


def test_homebrew_tools_of_the_builder_are_not_visible(sandbox: Sandbox) -> None:
    assert sandbox.run("command -v brew")[0] != 0
