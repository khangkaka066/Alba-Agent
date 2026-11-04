"""Builds the trusted probe that runs a task's pre-existing tests inside the sandbox.

The probe is written by the supervisor as its own script right before it runs, so code produced by the coder
cannot edit it. It refuses to run when a protected test file's hash differs from the staged one.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .evidence import Evidence, Level

_MARKER = "NEXUS_EVIDENCE"
_TEST_NAME = re.compile(r"^(test_[A-Za-z0-9_]*|[A-Za-z0-9_]*_test)\.py$")

_PROBE = '''\
import hashlib, io, json, os, sys, unittest
sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())
PROTECTED = json.loads(__PROTECTED__)
NONCE = __NONCE__


def digest(name):
    try:
        with open(name, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


tampered = sorted(name for name, wanted in PROTECTED.items() if digest(name) != wanted)
passed = failed = 0
details = []
if not tampered:
    for name in sorted(PROTECTED):
        module = name[:-3].replace("/", ".")
        suite = unittest.defaultTestLoader.loadTestsFromName(module)
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        if result.testsRun:
            bad = list(result.failures) + list(result.errors)
            passed += result.testsRun - len(bad)
            failed += len(bad)
            for case, trace in bad[:5]:
                details.append(str(case) + ": " + trace.strip()[-500:])
            continue
        try:
            import pytest
        except ImportError:
            continue
        class Counter:
            def __init__(self):
                self.ok = 0
                self.bad = 0
            def pytest_runtest_logreport(self, report):
                if report.when == "call" and report.passed:
                    self.ok += 1
                elif report.failed:
                    self.bad += 1
                    details.append(report.nodeid + ": " + str(report.longrepr)[-500:])
        counter = Counter()
        pytest.main(["-q", "-p", "no:cacheprovider", name], plugins=[counter])
        passed += counter.ok
        failed += counter.bad
print()
print("NEXUS_EVIDENCE " + NONCE + " " + json.dumps(
    {"passed": passed, "failed": failed, "tampered": tampered, "details": details[:8]}))
'''


def protected_test_hashes(input_files: dict[str, bytes]) -> dict[str, str]:
    """SHA-256 of every staged file that looks like a test module."""
    return {
        name: hashlib.sha256(content).hexdigest()
        for name, content in input_files.items() if _TEST_NAME.match(PurePosixPath(name).name)
    }


def build_probe(protected: dict[str, str]) -> tuple[str, str]:
    """Return `(probe_source, nonce)`; the nonce is fresh per probe so stray output cannot pose as evidence."""
    nonce = uuid4().hex
    source = _PROBE.replace("__PROTECTED__", repr(json.dumps(protected, sort_keys=True))).replace("__NONCE__", repr(nonce))
    return source, nonce


def parse_probe_output(stdout: str, nonce: str) -> Evidence | None:
    """Read the last evidence line carrying this probe's nonce; anything else is ignored."""
    prefix = f"{_MARKER} {nonce} "
    for line in reversed(stdout.splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            raw = json.loads(line[len(prefix):])
            return Evidence(
                Level.EXISTING_TESTS, int(raw["passed"]), int(raw["failed"]),
                tuple(str(item) for item in raw.get("tampered", ())), tuple(str(item) for item in raw.get("details", ())),
            )
        except (ValueError, KeyError, TypeError):
            return None
    return None


_SELF_TEST_DRIVER = '''
import base64, json, os, re
NONCE = __NONCE__
BASELINE = {name: base64.b64decode(value) for name, value in json.loads(__BASELINE__).items()}
TEST_NAME = re.compile(r"^(test_[A-Za-z0-9_]*|[A-Za-z0-9_]*_test)\\.py$")
names = sorted(name for name in os.listdir(".") if name.endswith(".py") and os.path.isfile(name))
tests = [name for name in names if TEST_NAME.match(name)]
sources = [name for name in names if name not in tests and not name.startswith("attempt_")]
outcome = gate(os.getcwd(), sources, tests, BASELINE) if tests and sources else {"ran": 0, "passed": False, "discriminates": False, "mutants": 0, "killed": 0}
print()
print("NEXUS_EVIDENCE " + NONCE + " " + json.dumps(outcome))
'''


def build_self_test_probe(staged: dict[str, bytes]) -> tuple[str, str]:
    """Probe for tasks that ship no tests: judges the coder's own test files with the V3 gates.

    The mutation module is concatenated in so the container runs one self-contained script written by the supervisor.
    """
    nonce = uuid4().hex
    baseline = {name: base64.b64encode(content).decode("ascii") for name, content in staged.items() if name.endswith(".py")}
    driver = _SELF_TEST_DRIVER.replace("__NONCE__", repr(nonce)).replace("__BASELINE__", repr(json.dumps(baseline, sort_keys=True)))
    return (Path(__file__).with_name("mutation.py").read_text(encoding="utf-8") + "\n" + driver), nonce


def parse_self_test_output(stdout: str, nonce: str) -> Evidence | None:
    prefix = f"{_MARKER} {nonce} "
    for line in reversed(stdout.splitlines()):
        if not line.startswith(prefix):
            continue
        try:
            raw = json.loads(line[len(prefix):])
            ran, passed = int(raw["ran"]), bool(raw["passed"])
            return Evidence(
                Level.SELF_TESTS, ran if passed else 0, 0 if passed else ran,
                discriminates=bool(raw["discriminates"]), mutants=int(raw["mutants"]), killed=int(raw["killed"]),
            )
        except (ValueError, KeyError, TypeError):
            return None
    return None
