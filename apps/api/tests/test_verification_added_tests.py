"""Where a task ships tests, the node can require tests of the coder's own before a result counts as verified."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nexus_core_schema.models import NexusGenSandboxNodeSpec
from verification import Evidence, Status, build_probe, decide, parse_probe_output, protected_test_hashes

CODE = b"def double(x):\n    return x * 2\n\n\ndef halve(x):\n    return x // 2\n"
SHIPPED = b"import unittest\nfrom calc import double\n\n\nclass T(unittest.TestCase):\n    def test_double(self) -> None:\n        self.assertEqual(double(2), 4)\n"
OWN_GOOD = b"import unittest\nfrom calc import halve\n\n\nclass T(unittest.TestCase):\n    def test_a(self) -> None:\n        self.assertEqual(halve(4), 2)\n\n    def test_b(self) -> None:\n        self.assertEqual(halve(5), 2)\n\n    def test_c(self) -> None:\n        self.assertEqual(halve(0), 0)\n"
OWN_BAD = b"import unittest\nfrom calc import halve\n\n\nclass T(unittest.TestCase):\n    def test_wrong(self) -> None:\n        self.assertEqual(halve(5), 3)\n"


def _probe(workdir: Path, extra: dict[str, bytes]) -> Evidence:
    (workdir / "calc.py").write_bytes(CODE)
    (workdir / "test_calc.py").write_bytes(SHIPPED)
    for name, content in extra.items():
        target = workdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    source, nonce = build_probe(protected_test_hashes({"test_calc.py": SHIPPED}))
    done = subprocess.run([sys.executable, "-c", source], cwd=workdir, capture_output=True, text=True, timeout=60, check=False)
    evidence = parse_probe_output(done.stdout, nonce)
    assert evidence is not None
    return evidence


def test_the_probe_counts_only_tests_that_are_not_the_shipped_ones(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, {"test_own.py": OWN_GOOD, "pkg/test_deep.py": OWN_GOOD})
    assert (evidence.passed, evidence.failed) == (1, 0)
    assert (evidence.added_passed, evidence.added_failed) == (6, 0)


def test_without_the_requirement_shipped_tests_alone_still_verify(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, {})
    assert evidence.added_passed == 0
    assert decide(evidence, execution_ok=True).status is Status.VERIFIED


def test_a_required_count_holds_back_verification_and_says_what_to_add(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, {})
    verdict = decide(evidence, execution_ok=True, min_added_tests=3)
    assert verdict.status is Status.UNVERIFIED and "add at least 3" in verdict.reason and "only 0" in verdict.reason


def test_enough_passing_added_tests_satisfy_the_requirement(tmp_path: Path) -> None:
    assert decide(_probe(tmp_path, {"test_own.py": OWN_GOOD}), execution_ok=True, min_added_tests=3).status is Status.VERIFIED


def test_a_failing_added_test_blocks_verification_and_is_reported(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, {"test_own.py": OWN_GOOD, "test_bad.py": OWN_BAD})
    assert evidence.added_failed == 1 and any("(your test)" in item for item in evidence.details)
    verdict = decide(evidence, execution_ok=True, min_added_tests=3)
    assert verdict.status is Status.UNVERIFIED and "fail" in verdict.reason


def test_an_added_test_file_that_cannot_be_imported_counts_as_failing(tmp_path: Path) -> None:
    evidence = _probe(tmp_path, {"test_broken.py": b"import module_that_does_not_exist\n"})
    assert evidence.added_failed == 1


def test_shipped_failures_still_outrank_the_requirement(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_bytes(b"def double(x):\n    return x + 1\n")
    (tmp_path / "test_calc.py").write_bytes(SHIPPED)
    (tmp_path / "test_own.py").write_bytes(OWN_GOOD)
    source, nonce = build_probe(protected_test_hashes({"test_calc.py": SHIPPED}))
    done = subprocess.run([sys.executable, "-c", source], cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    evidence = parse_probe_output(done.stdout, nonce)
    assert evidence is not None and decide(evidence, execution_ok=True, min_added_tests=3).status is Status.FAILED


def _node(min_added_tests: int = 0) -> NexusGenSandboxNodeSpec:
    return NexusGenSandboxNodeSpec(id="n", label="n", coder_model="m", reviewer_model="m", verification_command="python -m compileall .", min_added_tests=min_added_tests)


def test_the_node_spec_defaults_to_no_requirement_and_bounds_it() -> None:
    assert _node().min_added_tests == 0
    assert _node(min_added_tests=3).min_added_tests == 3
    for bad in (-1, 21):
        try:
            _node(min_added_tests=bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} must be rejected")
