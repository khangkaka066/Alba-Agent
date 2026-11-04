"""Classify why a run's product fell short and which part of the team structure is responsible."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from nexus_core_schema.models import NexusGenSandboxNodeSpec, CrewNodeSpec, RouterNodeSpec, WorkflowSpec

from .domains import SECTION_DIRECTORIES, domain_matches, is_code_or_media, role_from_path, uncovered_terms
from .models import BottleneckKind, BottleneckReport, Diagnosis, RunObservation

OVERLOAD_PATHS = 5
OVERLOAD_PATHS_PER_AGENT = 3
SLOW_NODE_FACTOR = 2.0
COST_SHARE_LIMIT = 0.30
NEGATIVE_TRANSFER_THETA = 0.2
TIMEOUT_PATTERN = re.compile(r"time(?:d)?[- ]?out|too long|exceeded|deadline", re.IGNORECASE)


def _agent_text(node: CrewNodeSpec | NexusGenSandboxNodeSpec) -> str:
    if isinstance(node, NexusGenSandboxNodeSpec):
        return f"{node.label} {node.coder_instructions} {node.reviewer_instructions} {' '.join(node.expected_artifact_paths)}"
    parts = [node.label]
    parts += [f"{agent.role} {agent.goal}" for agent in node.agents]
    parts += [f"{task.description} {' '.join(task.expected_artifact_paths)}" for task in node.tasks]
    parts += list(node.expected_artifact_paths)
    return " ".join(parts)


def declared_paths(node: CrewNodeSpec | NexusGenSandboxNodeSpec) -> tuple[str, ...]:
    return node.declared_artifact_paths()


class BottleneckAnalyzer:
    """Deterministic, explainable root-cause classification over one or more finished runs."""

    def __init__(self, theta: float = NEGATIVE_TRANSFER_THETA) -> None:
        self._theta = theta

    def analyze(
        self, spec: WorkflowSpec, runs: Sequence[RunObservation], transfer_scores: Mapping[str, float] | None = None,
    ) -> BottleneckReport:
        nodes = {node.id: node for node in spec.nodes}
        work_nodes = {node_id: node for node_id, node in nodes.items() if isinstance(node, (CrewNodeSpec, NexusGenSandboxNodeSpec))}
        failures: dict[str, dict[str, Any]] = defaultdict(lambda: {"runs": 0, "paths": [], "ok": [], "evidence": [], "timeout": False})
        aspects: dict[str, list[tuple[str, str]]] = defaultdict(list)
        gate_ids = [node.id for node in spec.nodes if isinstance(node, RouterNodeSpec) and node.artifact_gate]
        for run in runs:
            seen: set[str] = set()
            for node_id, node in work_nodes.items():
                output = run.node_outputs.get(node_id)
                contract = output.get("artifact_contract") if isinstance(output, Mapping) else None
                if isinstance(contract, Mapping):
                    bad = [str(path) for path in (*contract.get("missing", ()), *contract.get("invalid", ()))]
                    good = [str(path) for path in (*contract.get("verified", ()), *contract.get("recovered", ()))]
                    if bad:
                        record = failures[node_id]
                        record["paths"] += [path for path in bad if path not in record["paths"]]
                        record["ok"] += [path for path in good if path not in record["ok"]]
                        record["evidence"].append(f"run {run.run_id[:8]}: missing or invalid {', '.join(bad[:4])}")
                        seen.add(node_id)
                if isinstance(output, Mapping) and output.get("gate_passed") is False:
                    named = str(output.get("failing_department") or node_id)
                    seen.add(named if named in work_nodes else node_id)
                    failures[named if named in work_nodes else node_id]["evidence"].append(f"run {run.run_id[:8]}: QA critique failed this department")
                    for risk in (output.get("open_risks"), output.get("summary")):
                        if isinstance(risk, str):
                            aspects[named if named in work_nodes else node_id].append(("qa", risk))
            for gate_id in gate_ids:
                verdict = run.node_outputs.get(f"{gate_id}__gate")
                if isinstance(verdict, Mapping) and not verdict.get("gate_passed", True):
                    named = str(verdict.get("failing_department") or "")
                    target = named if named in work_nodes else None
                    for reason in verdict.get("reasons", ()):
                        aspects[target or gate_id].append(("gate", str(reason)))
                    if target:
                        seen.add(target)
                        failures[target]["evidence"].append(f"run {run.run_id[:8]}: quality gate blamed {target}")
            for feedback in run.human_feedback:
                if feedback.decision == "approved" or not feedback.comment:
                    continue
                target = feedback.node_id if feedback.node_id in work_nodes else None
                aspects[target or "*"].append(("human", feedback.comment))
                if target:
                    seen.add(target)
                    failures[target]["evidence"].append(f"run {run.run_id[:8]}: reviewer {feedback.decision} - {feedback.comment[:120]}")
            if run.status == "failed" and run.failure_message:
                blamed = next((node_id for node_id in work_nodes if node_id in run.failure_message), None)
                if blamed:
                    seen.add(blamed)
                    failures[blamed]["evidence"].append(f"run {run.run_id[:8]} failed: {run.failure_message[:140]}")
                    failures[blamed]["timeout"] = failures[blamed]["timeout"] or bool(TIMEOUT_PATTERN.search(run.failure_message))
            for node_id in seen:
                failures[node_id]["runs"] += 1

        durations = {node_id: [run.node_seconds[node_id] for run in runs if node_id in run.node_seconds] for node_id in work_nodes}
        typical = median([sum(values) / len(values) for values in durations.values() if values]) if any(durations.values()) else 0.0
        all_text = " ".join(_agent_text(node) for node in work_nodes.values())
        diagnoses: list[Diagnosis] = []
        handled: set[str] = set()

        for node_id, record in failures.items():
            if node_id not in work_nodes or (not record["paths"] and not record["evidence"]):
                continue
            node = work_nodes[node_id]
            paths = tuple(dict.fromkeys(record["paths"]))
            owned = set(declared_paths(node))
            repeat = max(1, int(record["runs"]))
            evidence = tuple(dict.fromkeys(record["evidence"]))[:6]
            count = len(owned)
            agents = len(node.agents) - (1 if isinstance(node, CrewNodeSpec) and node.manager_agent_id else 0) if isinstance(node, CrewNodeSpec) else 1
            mean_seconds = sum(durations[node_id]) / len(durations[node_id]) if durations[node_id] else 0.0
            partial = bool(record["ok"]) and bool(paths)

            code_paths = tuple(path for path in paths if is_code_or_media(path))
            if isinstance(node, CrewNodeSpec) and code_paths:
                diagnoses.append(Diagnosis(
                    kind=BottleneckKind.MISSING_SANDBOX_OR_VERIFICATION_GATE, node_id=node_id, severity=0.9, repeat_count=repeat,
                    evidence=(*evidence, f"{node.label} must produce code or media but has no isolated sandbox that executes and verifies it"),
                    failed_paths=code_paths,
                ))
                handled.add(node_id)
                continue
            overloaded = count >= OVERLOAD_PATHS or (agents > 0 and count / max(1, agents) >= OVERLOAD_PATHS_PER_AGENT)
            slow = bool(typical) and mean_seconds > SLOW_NODE_FACTOR * typical
            if overloaded and (partial or slow or record["timeout"]):
                diagnoses.append(Diagnosis(
                    kind=BottleneckKind.OVERLOADED_NODE_BOTTLENECK, node_id=node_id, severity=min(1.0, 0.6 + 0.05 * count),
                    repeat_count=repeat, failed_paths=paths,
                    evidence=(*evidence, f"{node.label} owns {count} deliverables across {max(1, agents)} agent(s)"
                              + (f" and takes {mean_seconds:.0f}s against a typical {typical:.0f}s" if slow else "")),
                ))
                handled.add(node_id)
                continue
            unowned = tuple(path for path in paths if path not in owned)
            texts = [text for _kind, text in (*aspects.get(node_id, ()), *aspects.get("*", ()))]
            missing_roles: list[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = []
            complaint = " ".join(texts)
            for domain in domain_matches(complaint):
                gaps = uncovered_terms(complaint, all_text, domain)
                if gaps:
                    missing_roles.append((domain.role, domain.goal, domain.path, domain.tools, tuple(gaps)))
            for path in unowned:
                role, vocabulary = role_from_path(path)
                if not any(token in all_text.lower() for token in vocabulary):
                    missing_roles.append((role, f"produce {path} for the department", path, ("report_exporter",), tuple(vocabulary)))
            if missing_roles and isinstance(node, CrewNodeSpec):
                role, goal, path, tools, terms = missing_roles[0]
                diagnoses.append(Diagnosis(
                    kind=BottleneckKind.MISSING_SPECIALIST_ROLE, node_id=node_id, severity=0.8, repeat_count=repeat,
                    failed_paths=paths, suggested_role=role, suggested_goal=goal, suggested_paths=(path,), suggested_tools=tools,
                    evidence=(*evidence, f"no agent in the team owns '{role}' work (flagged: {', '.join(terms)})"),
                ))
                handled.add(node_id)
                continue
            diagnoses.append(Diagnosis(
                kind=BottleneckKind.SKILL_OR_PROMPT_DEFICIT, node_id=node_id, severity=min(1.0, 0.4 + 0.15 * repeat), repeat_count=repeat,
                failed_paths=paths, evidence=(*evidence, "the right agent exists; its instructions or skills need refinement"),
                route_to="self_healing" if repeat < 2 else "topology",
            ))
            handled.add(node_id)

        # qa-detected aspects that no failing node explains but no agent covers either
        for target, items in aspects.items():
            if target in handled or (target == "*" and not items):
                continue
            complaint = " ".join(text for _kind, text in items)
            gap = next((domain for domain in domain_matches(complaint) if uncovered_terms(complaint, all_text, domain)), None)
            host = target if target in work_nodes and isinstance(work_nodes[target], CrewNodeSpec) else self._host_for(spec, gap.path if gap else "")
            if gap is not None and host is not None and host not in handled:
                diagnoses.append(Diagnosis(
                    kind=BottleneckKind.MISSING_SPECIALIST_ROLE, node_id=host, severity=0.7, repeat_count=1,
                    suggested_role=gap.role, suggested_goal=gap.goal, suggested_paths=(gap.path,), suggested_tools=gap.tools,
                    evidence=(f"quality review mentioned '{gap.keywords[0]}' but no agent owns that work",),
                ))
                handled.add(host)

        diagnoses += self._redundancy(spec, runs, work_nodes, transfer_scores or {})
        diagnoses.sort(key=lambda item: -item.severity)
        seconds = [run.run_seconds for run in runs if run.run_seconds is not None]
        return BottleneckReport(
            workflow_id=str(spec.id), runs_analyzed=len(runs), diagnoses=tuple(diagnoses),
            run_seconds=sum(seconds) / len(seconds) if seconds else 0.0,
        )

    @staticmethod
    def _host_for(spec: WorkflowSpec, suggested_path: str) -> str | None:
        """The department crew whose artifact directory best matches a missing specialist's output."""
        directory = suggested_path.split("/", 1)[0]
        crews = [node for node in spec.nodes if isinstance(node, CrewNodeSpec) and node.id != "direction"]
        for node in crews:
            owned = {path.split("/", 1)[0] for path in declared_paths(node)}
            if directory in owned or directory in SECTION_DIRECTORIES.get(node.id, ()):
                return node.id
        return crews[0].id if crews else None

    def _redundancy(
        self, spec: WorkflowSpec, runs: Sequence[RunObservation],
        work_nodes: Mapping[str, CrewNodeSpec | NexusGenSandboxNodeSpec], scores: Mapping[str, float],
    ) -> list[Diagnosis]:
        found: list[Diagnosis] = []
        total_cost = {node_id: sum(run.node_cost_usd.get(node_id, 0.0) for run in runs) for node_id in work_nodes}
        grand_total = sum(total_cost.values())
        referenced = " ".join(_agent_text(node) for node in work_nodes.values())
        for node_id, node in work_nodes.items():
            if not isinstance(node, CrewNodeSpec):
                continue
            busy = {task.agent_id for task in node.tasks}
            siblings = [agent for agent in node.agents if agent.id in busy and agent.id != node.manager_agent_id]
            for agent in node.agents:
                if agent.id == node.manager_agent_id:
                    continue
                if agent.id not in busy and len(node.agents) > 1:
                    found.append(Diagnosis(
                        kind=BottleneckKind.REDUNDANT_OR_NEGATIVE_AGENT, node_id=node_id, agent_id=agent.id, severity=0.5,
                        evidence=(f"{agent.role} has no task, so it adds prompt weight and cost without producing anything",),
                    ))
                elif scores.get(agent.id, 0.0) < -self._theta and len(siblings) > 1:
                    found.append(Diagnosis(
                        kind=BottleneckKind.REDUNDANT_OR_NEGATIVE_AGENT, node_id=node_id, agent_id=agent.id, severity=0.85,
                        evidence=(f"{agent.role} shows negative transfer (TIS {scores[agent.id]:.2f} < -{self._theta:.2f})",),
                    ))
            share = total_cost[node_id] / grand_total if grand_total else 0.0
            if (share >= COST_SHARE_LIMIT and not declared_paths(node) and node.id != "direction"
                    and node.id not in referenced.replace(node.label, "") and not node.id.endswith("_critic")):
                found.append(Diagnosis(
                    kind=BottleneckKind.REDUNDANT_OR_NEGATIVE_AGENT, node_id=node_id, severity=0.6,
                    evidence=(f"{node.label} accounts for {share:.0%} of spend, declares no deliverable and nothing downstream refers to it",),
                ))
        return found
