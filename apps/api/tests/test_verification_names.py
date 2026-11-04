"""Tests prove only the lines they run; the name scan catches a NameError hiding in a line they never reach."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from verification import Evidence, Status, build_probe, decide, parse_probe_output, protected_test_hashes
from verification.names import scan_undefined, undefined_names
from verification.probe import build_self_test_probe, parse_self_test_output

PASSING_TEST = b"import unittest\nfrom stock import reserve\n\n\nclass T(unittest.TestCase):\n    def test_ok(self) -> None:\n        self.assertEqual(reserve(5, 2), 3)\n"
# The shipped test never reaches the failing branch, which raises NameError the first time it runs.
BROKEN_STOCK = b"def reserve(have, want):\n    if want > have:\n        raise OutOfStock(want)\n    return have - want\n"
FIXED_STOCK = b"class OutOfStock(Exception):\n    pass\n\n\ndef reserve(have, want):\n    if want > have:\n        raise OutOfStock(want)\n    return have - want\n"


def test_a_name_that_is_read_and_never_bound_is_reported_with_file_and_line() -> None:
    assert undefined_names("def f(x):\n    return x + missing\n", "m.py") == ["m.py:2 missing"]


@pytest.mark.parametrize("source", [
    "import os\nprint(os.name)\n",
    "from os import path as p\nprint(p)\n",
    "import os.path\nprint(os)\n",
    "def f(a, *rest, k=1, **kw):\n    return a, rest, k, kw\n",
    "g = lambda x: x * 2\nprint(g(2))\n",
    "print([n for n in range(3) if n])\nprint({k: v for k, v in {1: 2}.items()})\n",
    "try:\n    pass\nexcept ValueError as error:\n    print(error)\n",
    "if (n := 3) > 2:\n    print(n)\n",
    "class A:\n    x = 1\n    y = x + 1\n",
    "def f():\n    global counter\n    counter = 1\n",
    "for i in range(3):\n    pass\nprint(i)\n",
    "with open('f') as handle:\n    print(handle)\n",
    "print(__name__, __file__, len, Exception)\n",
    "match 1:\n    case int() as number:\n        print(number)\n",
    "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from x import Thing\ndef f(a: 'Thing') -> 'Thing':\n    return a\n",
])
def test_names_bound_anywhere_or_built_in_are_not_reported(source: str) -> None:
    assert undefined_names(source, "m.py") == []


def test_star_imports_and_unparseable_files_report_nothing() -> None:
    assert undefined_names("from os import *\nprint(getcwd(), missing)\n") == []
    assert undefined_names("def broken(:\n") == []


def test_each_missing_name_is_listed_once_in_line_order() -> None:
    found = undefined_names("a = first\nb = second\nc = first\n", "m.py")
    assert found == ["m.py:1 first", "m.py:2 second"]


def test_the_scan_skips_tests_attempt_scripts_hidden_folders_and_reads_nested_packages(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text("x = nope\n")
    (tmp_path / "test_core.py").write_text("y = ignored_in_tests\n")
    (tmp_path / "attempt_3.py").write_text("z = ignored_attempt\n")
    (tmp_path / ".upstream").mkdir()
    (tmp_path / ".upstream" / "old.py").write_text("w = ignored_hidden\n")
    assert scan_undefined(str(tmp_path)) == ["pkg/core.py:1 nope"]


def _probe(workdir: Path, stock: bytes) -> Evidence | None:
    (workdir / "stock.py").write_bytes(stock)
    (workdir / "test_stock.py").write_bytes(PASSING_TEST)
    source, nonce = build_probe(protected_test_hashes({"test_stock.py": PASSING_TEST}))
    done = subprocess.run([sys.executable, "-c", source], cwd=workdir, capture_output=True, text=True, timeout=60, check=False)
    return parse_probe_output(done.stdout, nonce)


def test_passing_shipped_tests_no_longer_verify_code_with_an_undefined_name(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, BROKEN_STOCK)
    assert evidence is not None and evidence.passed == 1 and evidence.failed == 0
    verdict = decide(evidence, execution_ok=True)
    assert verdict.status is Status.FAILED and "OutOfStock" in verdict.reason and "stock.py:3" in verdict.reason
    assert verdict.as_dict()["undefined"] == ["stock.py:3 OutOfStock"]


def test_the_same_tests_verify_the_fixed_code(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, FIXED_STOCK)
    assert evidence is not None and evidence.undefined == ()
    assert decide(evidence, execution_ok=True).status is Status.VERIFIED


def test_the_self_test_probe_also_reports_undefined_names(tmp_path: Path) -> None:
    (tmp_path / "stock.py").write_bytes(BROKEN_STOCK)
    (tmp_path / "test_stock.py").write_bytes(PASSING_TEST)
    source, nonce = build_self_test_probe({"stock.py": BROKEN_STOCK})
    done = subprocess.run([sys.executable, "-c", source], cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    evidence = parse_self_test_output(done.stdout, nonce)
    assert evidence is not None and evidence.undefined == ("stock.py:3 OutOfStock",)
    assert decide(evidence, execution_ok=True).status is Status.FAILED
