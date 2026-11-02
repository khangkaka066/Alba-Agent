"""Lifecycle hooks that enforce artifact contracts, path-scoped standards and visual QA evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from nexus_core_schema.artifacts import artifact_file
from nexus_core_schema.models import PathRuleSpec

CheckStatus = Literal["verified", "recovered", "missing", "invalid"]

TEXT_SUFFIXES = frozenset({
    ".md", ".txt", ".py", ".ts", ".tsx", ".js", ".mjs", ".gd", ".cs", ".html", ".css", ".yaml", ".yml",
    ".csv", ".toml", ".srt", ".vtt", ".sql", ".sh", ".tscn", ".tres", ".cfg", ".ini", ".xml", ".svg",
})
DOCUMENT_SUFFIXES = frozenset({".md", ".txt", ".json"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".m4v", ".webm", ".mkv"})
MAX_RECOVERED_BYTES = 512_000
EVIDENCE_DIRECTORY = "qa/evidence"


def _signature_ok(suffix: str, head: bytes) -> bool:
    """Check the container signature of binary deliverables so placeholder files fail the contract."""
    if suffix == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if suffix in {".mp4", ".mov", ".m4v", ".m4a"}:
        return head[4:8] == b"ftyp"
    if suffix in {".webm", ".mkv"}:
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if suffix == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if suffix == ".mp3":
        return head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if suffix == ".zip":
        return head.startswith(b"PK\x03\x04")
    if suffix == ".pdf":
        return head.startswith(b"%PDF")
    return True


@dataclass(frozen=True)
class ArtifactCheck:
    path: str
    status: CheckStatus
    reason: str = ""
    size_bytes: int = 0


@dataclass(frozen=True)
class ArtifactContractReport:
    node_id: str
    checks: tuple[ArtifactCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.status in ("verified", "recovered") for check in self.checks)

    def paths(self, *statuses: CheckStatus) -> list[str]:
        return [check.path for check in self.checks if check.status in statuses]

    def as_output(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verified": self.paths("verified"),
            "recovered": self.paths("recovered"),
            "missing": self.paths("missing"),
            "invalid": self.paths("invalid"),
            "warnings": [f"{check.path}: {check.reason}" for check in self.checks if check.status != "verified" and check.reason],
        }


class ArtifactContractHook:
    """``validate_agent_artifact``: every declared path must exist, be non-empty and look like its type."""

    def validate_file(self, path: Path, relative: str) -> ArtifactCheck:
        if not path.is_file():
            return ArtifactCheck(relative, "missing", "The node finished without writing this file")
        size = path.stat().st_size
        if size == 0:
            return ArtifactCheck(relative, "invalid", "The file is empty", 0)
        suffix = path.suffix.lower()
        with path.open("rb") as handle:
            head = handle.read(16)
        if not _signature_ok(suffix, head):
            return ArtifactCheck(relative, "invalid", f"The file is not a valid {suffix} container", size)
        if suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return ArtifactCheck(relative, "invalid", "The file is not valid JSON", size)
        elif suffix in TEXT_SUFFIXES:
            try:
                if not path.read_text(encoding="utf-8").strip():
                    return ArtifactCheck(relative, "invalid", "The file contains only whitespace", size)
            except UnicodeDecodeError:
                return ArtifactCheck(relative, "invalid", "The text file is not UTF-8", size)
        return ArtifactCheck(relative, "verified", "", size)

    def validate_agent_artifact(
        self,
        directory: Path,
        node_id: str,
        paths: Sequence[str],
        structured_output: Mapping[str, Any] | None = None,
        sources: Mapping[str, bytes] | None = None,
    ) -> ArtifactContractReport:
        """Validate declared files, materialising sandbox exports and recovering conversational documents.

        ``sources`` holds bytes exported from the node's isolated computer. ``structured_output`` is the node's
        typed result; when an agent answered in text without writing a document (``.md``, ``.txt``, ``.json``),
        the hook writes that result to the declared path and records the recovery as a warning. Source code and
        media are never synthesised: a missing file stays missing so the quality gate sends the work back.
        """
        checks: list[ArtifactCheck] = []
        for relative in paths:
            try:
                target = artifact_file(directory, relative)
            except ValueError as error:
                checks.append(ArtifactCheck(relative, "invalid", str(error)))
                continue
            if not target.is_file() and sources and relative in sources and sources[relative]:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(sources[relative])
            check = self.validate_file(target, relative)
            if check.status != "verified" and structured_output and target.suffix.lower() in DOCUMENT_SUFFIXES:
                content = render_document(relative, structured_output)
                if content.strip() and len(content.encode("utf-8")) <= MAX_RECOVERED_BYTES:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                    recovered = self.validate_file(target, relative)
                    if recovered.status == "verified":
                        check = ArtifactCheck(
                            relative, "recovered",
                            f"The agent returned text instead of writing the file ({check.reason.lower()}); "
                            "its structured output was saved to the contract path",
                            recovered.size_bytes,
                        )
            checks.append(check)
        return ArtifactContractReport(node_id, tuple(checks))


def render_document(relative: str, output: Mapping[str, Any]) -> str:
    if relative.lower().endswith(".json"):
        return json.dumps(dict(output), ensure_ascii=False, indent=2) + "\n"
    title = Path(relative).stem.replace("_", " ").replace("-", " ").strip().title() or "Deliverable"
    lines = [f"# {title}", ""]
    for key, value in output.items():
        if key == "artifact_contract":
            continue
        lines.append(f"## {key.replace('_', ' ').title()}")
        lines.append("")
        if isinstance(value, (dict, list)):
            lines.append("```json")
            lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines)


def _glob_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(parts) + "$")


DEFAULT_PATH_RULES: tuple[PathRuleSpec, ...] = (
    PathRuleSpec(pattern="design/**", rule="Design documents state the decision, the reason, the alternatives rejected and testable acceptance criteria. Number sections so other departments can cite them."),
    PathRuleSpec(pattern="src/**", rule="Source files are complete and runnable: no placeholders, TODO stubs or invented APIs. Keep secrets, credentials and network calls out of source code."),
    PathRuleSpec(pattern="src/gameplay/**", rule="Gameplay code uses a fixed-timestep update, keeps tuning values in data files, and never couples game rules to rendering or frame rate."),
    PathRuleSpec(pattern="src/ui/**", rule="UI code reads text from localisation keys, supports keyboard navigation and readable contrast, and never blocks the main loop."),
    PathRuleSpec(pattern="tests/**", rule="Tests are deterministic and offline, assert observable behaviour, and name the requirement they verify."),
    PathRuleSpec(pattern="media/**", rule="Media files record resolution, duration and source in the production log. Use only generated or licensed material and no real person's likeness or voice without documented consent."),
    PathRuleSpec(pattern="qa/evidence/**", rule="Evidence files are real captures of the delivered build or render, named after the artifact they verify. Never submit a mock-up as evidence."),
    PathRuleSpec(pattern="release/**", rule="Release bundles contain only verified artifacts, a manifest with checksums and the approval reference."),
)


class PathScopedRuleInjector:
    """Inject domain standards based on the artifact paths an agent or sandbox is responsible for."""

    def __init__(self, rules: Iterable[PathRuleSpec] = ()) -> None:
        merged = {(rule.pattern, rule.rule): rule for rule in (*DEFAULT_PATH_RULES, *rules)}
        self._rules = [(rule, _glob_regex(rule.pattern)) for rule in merged.values()]

    def rules_for(self, paths: Iterable[str]) -> list[str]:
        targets = list(paths)
        return [rule.rule for rule, matcher in self._rules if any(matcher.match(path) for path in targets)]

    def instruction_block(self, paths: Iterable[str]) -> str:
        targets = list(dict.fromkeys(paths))
        if not targets:
            return ""
        rules = self.rules_for(targets)
        block = "Required deliverables (write each file at exactly this run-relative path):\n" + "\n".join(f"- {path}" for path in targets)
        if rules:
            block += "\n\nPath-scoped standards:\n" + "\n".join(f"- {rule}" for rule in rules)
        return block


@dataclass(frozen=True)
class VisualEvidenceReport:
    passed: bool
    files: tuple[str, ...] = ()
    reason: str = ""

    def as_output(self) -> dict[str, Any]:
        return {"passed": self.passed, "files": list(self.files), "reason": self.reason}


class VisualEvidenceHook:
    """UI, game, web and video work passes the gate only with a real rendered preview in ``qa/evidence/``."""

    def __init__(self, contract: ArtifactContractHook | None = None) -> None:
        self._contract = contract or ArtifactContractHook()

    def check(self, directory: Path) -> VisualEvidenceReport:
        evidence = directory / EVIDENCE_DIRECTORY
        if not evidence.is_dir():
            return VisualEvidenceReport(False, (), f"No rendered preview was saved in {EVIDENCE_DIRECTORY}/")
        valid: list[str] = []
        for path in sorted(evidence.rglob("*")):
            suffix = path.suffix.lower()
            if path.is_symlink() or not path.is_file() or suffix not in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
                continue
            relative = path.relative_to(directory).as_posix()
            if self._contract.validate_file(path, relative).status == "verified":
                valid.append(relative)
        if not valid:
            return VisualEvidenceReport(False, (), f"{EVIDENCE_DIRECTORY}/ holds no valid screenshot or video frame")
        return VisualEvidenceReport(True, tuple(valid))


@dataclass
class GateVerdict:
    gate_passed: bool
    failing_department: str | None
    missing: list[str] = field(default_factory=list)
    visual_evidence: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)

    def as_output(self) -> dict[str, Any]:
        return {
            "gate_passed": self.gate_passed, "failing_department": self.failing_department,
            "missing": self.missing, "visual_evidence": self.visual_evidence, "reasons": self.reasons,
        }


class LifecycleHookEngine:
    """Runs the artifact, path-rule and visual-evidence hooks for one workflow run."""

    def __init__(self, path_rules: Iterable[PathRuleSpec] = ()) -> None:
        self.contract = ArtifactContractHook()
        self.rules = PathScopedRuleInjector(path_rules)
        self.visual = VisualEvidenceHook(self.contract)

    def after_node(
        self,
        directory: Path,
        node_id: str,
        paths: Sequence[str],
        structured_output: Mapping[str, Any] | None = None,
        sources: Mapping[str, bytes] | None = None,
    ) -> ArtifactContractReport:
        directory.mkdir(parents=True, exist_ok=True)
        return self.contract.validate_agent_artifact(directory, node_id, paths, structured_output, sources)

    def evaluate_gate(
        self,
        directory: Path,
        node_outputs: Mapping[str, Any],
        ownership: Mapping[str, Sequence[str]],
        node_order: Sequence[str],
        rework_targets: Sequence[str],
        visual_required: bool,
    ) -> GateVerdict:
        """Combine artifact contracts, visual evidence and QA verdicts into one routing decision.

        ``ownership`` maps node IDs to their declared paths and ``node_order`` lists nodes topologically.
        The failing department is the earliest rework target that owns a missing path (or that a QA crew
        named explicitly); ``None`` means no single department can be blamed and the gate escalates.
        """
        missing: list[str] = []
        reasons: list[str] = []
        blamed: list[str] = []
        for node_id in node_order:
            output = node_outputs.get(node_id)
            if not isinstance(output, Mapping):
                continue
            contract = output.get("artifact_contract")
            if isinstance(contract, Mapping) and not contract.get("passed", True):
                failed = [*contract.get("missing", ()), *contract.get("invalid", ())]
                missing.extend(str(path) for path in failed)
                reasons.append(f"{node_id} is missing or produced invalid files: {', '.join(map(str, failed))}")
                blamed.append(node_id)
            if output.get("gate_passed") is False:
                named = output.get("failing_department")
                reasons.append(f"{node_id} reported a failed quality review" + (f" for {named}" if named else ""))
                if isinstance(named, str) and named:
                    blamed.append(named)
                else:
                    blamed.append(node_id)
        visual: VisualEvidenceReport | None = None
        if visual_required:
            visual = self.visual.check(directory)
            if not visual.passed:
                reasons.append(visual.reason)
                evidence_owners = [node_id for node_id in node_order if any(
                    path.startswith(f"{EVIDENCE_DIRECTORY}/") for path in ownership.get(node_id, ())
                )]
                blamed.extend(evidence_owners or [f"{EVIDENCE_DIRECTORY}/"])
                missing.append(f"{EVIDENCE_DIRECTORY}/")
        failing = next((node_id for node_id in node_order if node_id in blamed and node_id in rework_targets), None)
        return GateVerdict(
            gate_passed=not reasons, failing_department=failing if reasons else None,
            missing=list(dict.fromkeys(missing)), visual_evidence=visual.as_output() if visual else None,
            reasons=reasons,
        )
