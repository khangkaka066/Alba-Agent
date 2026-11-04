"""Two failures a large multi-node task exposed: a node verified by another node's files, and a long request breaking capsule creation."""

from __future__ import annotations

from uuid import uuid4

from learning_transfer.distiller import MAX_HEURISTIC, MAX_PRECONDITIONS, DistillationCandidate, DistillationTrigger, EpisodicKnowledgeDistiller
from nexusgen_bridge.sandbox_team import require_declared_files
from verification import Evidence, Level, Status, VerificationReport

VERIFIED = VerificationReport(Status.VERIFIED, Level.SELF_TESTS, "6 self-written tests pass", Evidence(Level.SELF_TESTS, 6, 0))


def test_a_node_is_not_verified_until_its_own_declared_files_exist() -> None:
    report = require_declared_files(VERIFIED, ("parser.py", "test_parser.py"), ("tokenizer.py", "test_tokenizer.py", "errors.py"))
    assert report.status is Status.UNVERIFIED
    assert "parser.py" in report.reason and "test_parser.py" in report.reason and "other nodes do not count" in report.reason
    assert report.evidence is VERIFIED.evidence and report.level is Level.SELF_TESTS


def test_declared_files_that_are_present_leave_the_verdict_alone() -> None:
    assert require_declared_files(VERIFIED, ("parser.py",), ("./parser.py", "errors.py")) is VERIFIED
    assert require_declared_files(VERIFIED, ("pkg/mod.py",), ("pkg/mod.py",)) is VERIFIED


def test_nodes_without_declared_files_and_results_that_are_not_verified_are_untouched() -> None:
    assert require_declared_files(VERIFIED, (), ()) is VERIFIED
    failed = VerificationReport(Status.FAILED, Level.NONE, "did not run", None)
    assert require_declared_files(failed, ("a.py",), ()) is failed


def _candidate(preconditions: str, heuristic: str) -> DistillationCandidate:
    return DistillationCandidate(
        tenant_id=uuid4(), workspace_id=uuid4(), source_agent_id="solo_coder", source_role="coding and verification",
        trigger=DistillationTrigger.DEBUG_RECOVERY, heuristic=heuristic, preconditions=preconditions,
        domain_tags=("python",), debug_turns=3,
    )


def test_a_long_request_still_yields_a_capsule_instead_of_failing_the_run() -> None:
    capsule = EpisodicKnowledgeDistiller().distill(_candidate("x" * 9000, "y" * 20000))
    assert capsule is not None
    assert len(capsule.trigger_preconditions) == MAX_PRECONDITIONS and len(capsule.distilled_heuristic) == MAX_HEURISTIC


def test_short_text_is_kept_whole() -> None:
    capsule = EpisodicKnowledgeDistiller().distill(_candidate("  fix the ledger  ", "round half up"))
    assert capsule is not None and capsule.trigger_preconditions == "fix the ledger" and capsule.distilled_heuristic == "round half up"
