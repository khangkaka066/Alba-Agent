"""A task may ship a package directory, not only flat files."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from flows.compiler import sandbox_input_path_error
from verification.probe import build_probe, protected_test_hashes


@pytest.mark.parametrize("name", ["a.py", "pkg/mod.py", "pkg/sub/mod.py", "tests/test_mod.py", ".hidden/x", "a b/c d.txt"])
def test_relative_paths_are_accepted(name: str) -> None:
    assert sandbox_input_path_error(name) is None


@pytest.mark.parametrize("name", [
    "", "/etc/passwd", "../x", "a/../../x", "a/./b", "a//b", "a/", "dir\\file.py", "a\x00b", "x" * 201, "/".join(["d"] * 9) + "/f.py",
])
def test_paths_that_leave_the_working_directory_are_refused(name: str) -> None:
    assert sandbox_input_path_error(name)


def test_nested_test_modules_are_protected_by_their_file_name() -> None:
    staged = {"tests/test_mod.py": b"x", "pkg/mod.py": b"y", "pkg/helper_test.py": b"z", "notes/test_notes.txt": b"n"}
    assert set(protected_test_hashes(staged)) == {"tests/test_mod.py", "pkg/helper_test.py"}


def test_the_probe_runs_a_test_module_that_lives_in_a_folder(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def double(x):\n    return x * 2\n")
    (tmp_path / "tests").mkdir()
    test_source = (
        "import unittest\nfrom pkg.mod import double\n\n\nclass T(unittest.TestCase):\n"
        "    def test_double(self):\n        self.assertEqual(double(2), 4)\n"
    )
    (tmp_path / "tests" / "test_mod.py").write_text(test_source)
    source, nonce = build_probe(protected_test_hashes({"tests/test_mod.py": test_source.encode()}))
    (tmp_path / "probe.py").write_text(source)
    done = subprocess.run([sys.executable, "probe.py"], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    line = next(item for item in done.stdout.splitlines() if item.startswith("NEXUS_EVIDENCE "))
    evidence = json.loads(line.split(" ", 2)[2])
    assert line.split(" ", 2)[1] == nonce
    assert (evidence["passed"], evidence["failed"], evidence["tampered"]) == (1, 0, [])
