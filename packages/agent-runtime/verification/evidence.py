"""Evidence bundle and the pure function that turns it into a verification state.

The reviewer model never appears here: a state is decided only from executed checks.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    NONE = "none"
    EXISTING_TESTS = "v1_existing_tests"
    SELF_TESTS = "v3_self_tests"


class Status(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    FAILED = "failed"


@dataclass(frozen=True)
class Evidence:
    level: Level
    passed: int
    failed: int
    tampered: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    # Only for self-written tests: do they fail on the starting code, and how many code mutants do they catch.
    discriminates: bool = False
    mutants: int = 0
    killed: int = 0
    # `file:line name` for names the program files read but never define: tests cannot vouch for lines they do not run.
    undefined: tuple[str, ...] = ()
    # Test files the coder added next to the protected ones, and how they fared.
    added_passed: int = 0
    added_failed: int = 0

    @property
    def ran(self) -> int:
        return self.passed + self.failed


@dataclass(frozen=True)
class VerificationReport:
    status: Status
    level: Level
    reason: str
    evidence: Evidence | None = None

    def as_dict(self) -> dict[str, object]:
        evidence = self.evidence
        return {
            "status": self.status.value,
            "level": self.level.value,
            "reason": self.reason,
            "passed": evidence.passed if evidence else 0,
            "failed": evidence.failed if evidence else 0,
            "tampered": list(evidence.tampered) if evidence else [],
            "details": list(evidence.details) if evidence else [],
            "mutants": evidence.mutants if evidence else 0,
            "killed": evidence.killed if evidence else 0,
            "undefined": list(evidence.undefined) if evidence else [],
            "added_passed": evidence.added_passed if evidence else 0,
            "added_failed": evidence.added_failed if evidence else 0,
        }


_COMPILE_ONLY = re.compile(r"^python3?(\.\d+)?\s+-m\s+(compileall|py_compile)\b")


def is_compile_only(command: str) -> bool:
    """True when every `&&`-joined step only compiles or no-ops; compiling proves nothing about behaviour."""
    steps = [part.strip() for part in re.split(r"&&|;", command) if part.strip()]
    if not steps:
        return True
    for step in steps:
        try:
            words = shlex.split(step)
        except ValueError:
            return False
        if words and words[0] in ("true", ":", "echo", "cd"):
            continue
        if not _COMPILE_ONLY.match(step):
            return False
    return True


# Self-written tests are weaker than a task's own tests, so they must clear every gate below to count.
MIN_SELF_TESTS = 3
MIN_MUTANTS = 3
MIN_KILL_RATIO = 0.5


def _decide_self_tests(evidence: Evidence) -> VerificationReport:
    level = Level.SELF_TESTS
    if evidence.ran < MIN_SELF_TESTS:
        return VerificationReport(Status.UNVERIFIED, level, f"only {evidence.ran} self-written tests exist; at least {MIN_SELF_TESTS} are required", evidence)
    if evidence.failed:
        return VerificationReport(Status.UNVERIFIED, level, f"{evidence.failed} of the coder's own tests fail", evidence)
    if not evidence.discriminates:
        return VerificationReport(Status.UNVERIFIED, level, "the self-written tests also pass on the starting code, so they prove nothing", evidence)
    if evidence.mutants < MIN_MUTANTS:
        return VerificationReport(Status.UNVERIFIED, level, "the code has too few mutation sites to measure how strong the tests are", evidence)
    if evidence.killed < evidence.mutants * MIN_KILL_RATIO:
        return VerificationReport(Status.UNVERIFIED, level, f"the self-written tests caught only {evidence.killed} of {evidence.mutants} code mutants", evidence)
    return VerificationReport(Status.VERIFIED, level, f"{evidence.passed} self-written tests pass, fail on the starting code and caught {evidence.killed} of {evidence.mutants} mutants", evidence)


def decide(evidence: Evidence | None, *, execution_ok: bool, min_added_tests: int = 0) -> VerificationReport:
    """Verified only by executed tests that all passed; compile or review output is never evidence.

    `min_added_tests` asks, for tasks that ship tests, for that many passing tests of the coder's own on top of the shipped
    ones: shipped tests cover only part of what the task states, and writing a test per remaining clause is how the rest is checked.
    """
    if evidence is not None and evidence.tampered:
        return VerificationReport(Status.FAILED, evidence.level, f"protected test files were changed: {', '.join(evidence.tampered)}", evidence)
    if evidence is not None and evidence.undefined:
        shown = ", ".join(evidence.undefined[:5])
        return VerificationReport(Status.FAILED, evidence.level, f"the code reads names that are never defined or imported ({shown}); that raises NameError when the line runs", evidence)
    if evidence is not None and evidence.level is Level.SELF_TESTS and execution_ok:
        return _decide_self_tests(evidence)
    if evidence is None or evidence.ran == 0:
        if not execution_ok:
            return VerificationReport(Status.FAILED, Level.NONE, "the code did not run cleanly and no tests exist", evidence)
        return VerificationReport(Status.UNVERIFIED, Level.NONE, "the code ran but no executable test exists to prove it correct", evidence)
    if evidence.failed:
        return VerificationReport(Status.FAILED, evidence.level, f"{evidence.failed} of {evidence.ran} existing tests failed", evidence)
    if min_added_tests and evidence.level is Level.EXISTING_TESTS:
        if evidence.added_failed:
            return VerificationReport(Status.UNVERIFIED, evidence.level, f"{evidence.added_failed} of the tests you added fail; fix the code or the test", evidence)
        if evidence.added_passed < min_added_tests:
            return VerificationReport(
                Status.UNVERIFIED, evidence.level,
                f"the shipped tests pass but only {evidence.added_passed} test(s) of your own exist; add at least {min_added_tests} in a new test_*.py file, "
                "one for each clause of the task or the docstrings that the shipped tests never exercise", evidence)
    return VerificationReport(Status.VERIFIED, evidence.level, f"all {evidence.passed} existing tests passed", evidence)
