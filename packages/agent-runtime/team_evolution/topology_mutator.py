"""Deterministic, schema-validated structural mutations of a workflow's team topology (vN -> vN+1)."""

from __future__ import annotations

import copy
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from agent_skills import SkillLoader
from nexus_core_schema.models import WorkflowSpec

from .domains import discover_skills, discover_tools, is_code_or_media, suffix_of
from .layout import layered_layout
from .models import (
    AppliedOp,
    InjectQuality,
    MutationOp,
    OpKind,
    PruneOrMerge,
    RewireParallel,
    SpawnSpecialist,
    SplitOverloaded,
    TopologyDiff,
)

Doc = dict[str, Any]
JOINABLE = ("crew", "sandbox")
DEPENDENCY_WORDS = re.compile(r"\b(upstream|previous|prior|preceding|earlier nodes?|above|completed node)\b", re.IGNORECASE)


class MutationError(ValueError):
    """A requested structural change is unsafe or does not apply to the workflow."""


@dataclass
class MutationResult:
    spec: WorkflowSpec
    applied: list[AppliedOp]
    diff: TopologyDiff
    skipped: list[str] = field(default_factory=list)


def _slug(value: str, limit: int = 40) -> str:
    return (re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_") or "node")[:limit]


def _deliverable_schema(name: str, *, gate: bool = False) -> Doc:
    properties: Doc = {
        "summary": {"type": "string"}, "content": {"type": "string"},
        "files_written": {"type": "array", "items": {"type": "string"}}, "open_risks": {"type": "string"},
    }
    required = ["summary", "content", "files_written"]
    if gate:
        properties["gate_passed"] = {"type": "boolean"}
        properties["failing_department"] = {"type": "string"}
        required += ["gate_passed", "failing_department"]
    return {"title": name, "type": "object", "additionalProperties": False, "properties": properties, "required": required}


def _schema_name(*parts: str) -> str:
    return "Evolved" + "".join(re.sub(r"[^A-Za-z0-9]", "", part.title()) for part in parts) + "Output"


class TeamTopologyMutator:
    """Applies mutation operators to a ``WorkflowSpec`` and returns a validated next-version spec."""

    def __init__(
        self,
        available_tools: Collection[str] | None = None,
        available_models: Sequence[str] = (),
        available_skills: Collection[str] | None = None,
        skill_loader: SkillLoader | None = None,
    ) -> None:
        self._tools = available_tools
        self._models = tuple(available_models)
        self._skills = available_skills
        self._loader = skill_loader or SkillLoader()

    # --- public ------------------------------------------------------------------------------------------------

    def apply(self, spec: WorkflowSpec, operations: Sequence[MutationOp], *, next_version: int | None = None,
              new_id: UUID | None = None, strict: bool = True) -> MutationResult:
        """Apply operations in order. With ``strict=False`` an operation that cannot apply is skipped and reported."""
        doc: Doc = spec.model_dump(mode="json")
        applied: list[AppliedOp] = []
        skipped: list[str] = []
        for operation in operations:
            snapshot = copy.deepcopy(doc)
            try:
                record = self._dispatch(doc, operation)
                WorkflowSpec.model_validate(self._finalize(copy.deepcopy(doc), spec, next_version, new_id))
            except (MutationError, ValueError, KeyError) as error:
                doc = snapshot
                if strict:
                    raise MutationError(f"{operation.op} on {operation.target_node_id}: {error}") from error
                skipped.append(f"{operation.op} on {operation.target_node_id}: {error}")
                continue
            applied.append(record.model_copy(update={"request": operation.model_dump(mode="json")}))
        if not applied:
            raise MutationError("No mutation could be applied" + (": " + "; ".join(skipped) if skipped else ""))
        evolved = WorkflowSpec.model_validate(self._finalize(doc, spec, next_version, new_id))
        from flows.compiler import FlowCompiler

        FlowCompiler.validate(evolved)
        return MutationResult(evolved, applied, diff_specs(spec, evolved), skipped)

    def _finalize(self, doc: Doc, base: WorkflowSpec, next_version: int | None, new_id: UUID | None) -> Doc:
        previous = {node_id: position for node_id, position in doc.get("layout", {}).items()}
        doc["layout"] = layered_layout([node["id"] for node in doc["nodes"]], doc["edges"], previous)
        doc["version"] = next_version if next_version is not None else base.version + 1
        doc["id"] = str(new_id or uuid4())
        agent_ids = {agent["id"] for node in doc["nodes"] if node["kind"] == "crew" for agent in node["agents"]}
        valid_sources = agent_ids | {f"{node['id']}_coder" for node in doc["nodes"] if node["kind"] == "sandbox"}
        doc["learning_edges"] = [
            edge for edge in doc.get("learning_edges", ())
            if edge["source_agent_id"] in valid_sources and edge["target_agent_id"] in agent_ids
        ]
        return doc

    def _dispatch(self, doc: Doc, operation: MutationOp) -> AppliedOp:
        if isinstance(operation, SpawnSpecialist):
            return self._spawn(doc, operation)
        if isinstance(operation, SplitOverloaded):
            return self._split(doc, operation)
        if isinstance(operation, InjectQuality):
            return self._inject(doc, operation)
        if isinstance(operation, PruneOrMerge):
            return self._prune(doc, operation)
        return self._rewire(doc, operation)

    # --- graph helpers -----------------------------------------------------------------------------------------

    @staticmethod
    def _node(doc: Doc, node_id: str, *kinds: str) -> Doc:
        node: Doc | None = next((item for item in doc["nodes"] if item["id"] == node_id), None)
        if node is None:
            raise MutationError(f"Node {node_id} does not exist")
        if kinds and node["kind"] not in kinds:
            raise MutationError(f"Node {node_id} is a {node['kind']} node; expected {' or '.join(kinds)}")
        return node

    @staticmethod
    def _forward(doc: Doc) -> list[Doc]:
        return [edge for edge in doc["edges"] if not edge.get("loop_back")]

    @staticmethod
    def _unique(taken: Collection[str], base: str) -> str:
        candidate, counter = base, 2
        while candidate in taken:
            candidate, counter = f"{base}_{counter}", counter + 1
        return candidate

    @staticmethod
    def _declared(node: Doc) -> list[str]:
        paths = list(node.get("expected_artifact_paths", ()))
        for task in node.get("tasks", ()):
            paths += task.get("expected_artifact_paths", ())
        return list(dict.fromkeys(paths))

    def _all_declared(self, doc: Doc) -> set[str]:
        return {path for node in doc["nodes"] if node["kind"] in JOINABLE for path in self._declared(node)}

    @staticmethod
    def _retarget_gate(doc: Doc, old_id: str, new_ids: Sequence[str]) -> None:
        """Keep artifact-gate routes and rework loop-back edges pointing at the nodes that now own the work."""
        for gate in (node for node in doc["nodes"] if node["kind"] == "router"):
            old_routes = [route for route in gate["routes"] if route.get("value") == old_id]
            if not old_routes:
                continue
            gate["routes"] = [route for route in gate["routes"] if route.get("value") != old_id]
            template = old_routes[0]
            old_names = {route["name"] for route in old_routes}
            loop_edges = [edge for edge in doc["edges"] if edge["source"] == gate["id"] and edge.get("loop_back") and edge.get("route") in old_names]
            doc["edges"] = [edge for edge in doc["edges"] if edge not in loop_edges]
            existing = {route["name"] for route in gate["routes"]} | {gate["default_route"]}
            for new_id in new_ids:
                name = f"rework_{new_id}"
                if name in existing:
                    continue
                gate["routes"].append({**template, "name": name, "value": new_id})
                existing.add(name)
                if loop_edges:
                    doc["edges"].append({"source": gate["id"], "target": new_id, "route": name, "loop_back": True})

    @staticmethod
    def _detach(doc: Doc, node_id: str) -> list[Doc]:
        """Remove every forward edge touching ``node_id`` and return them."""
        removed = [edge for edge in doc["edges"] if not edge.get("loop_back") and node_id in (edge["source"], edge["target"])]
        doc["edges"] = [edge for edge in doc["edges"] if edge not in removed]
        return removed

    @staticmethod
    def _require_joinable(doc: Doc, node_ids: Collection[str]) -> bool:
        kinds = {node["id"]: node["kind"] for node in doc["nodes"]}
        return all(kinds[node_id] in JOINABLE for node_id in node_ids)

    # --- 1. spawn ----------------------------------------------------------------------------------------------

    def _spawn(self, doc: Doc, op: SpawnSpecialist) -> AppliedOp:
        node = self._node(doc, op.target_node_id, "crew")
        taken_agents = {agent["id"] for item in doc["nodes"] if item["kind"] == "crew" for agent in item["agents"]}
        taken_paths = self._all_declared(doc)
        clashes = [path for path in op.expected_artifact_paths if path in taken_paths]
        if clashes:
            raise MutationError(f"Artifact path already owned by another task: {', '.join(clashes)}")
        specialists = [agent for agent in node["agents"] if agent["id"] != node.get("manager_agent_id")]
        model = op.model or (specialists[0]["model"] if specialists else node["agents"][0]["model"])
        text = f"{op.role} {op.goal} {op.task_description}"
        tools = discover_tools(text, self._tools, op.tool_ids)
        skills = op.skill_ids or discover_skills(text, self._loader, self._skills)
        agent_id = self._unique(taken_agents, f"{node['id']}_{_slug(op.role)}")
        schema = _schema_name(node["id"], op.role)
        node["agents"].append({
            "id": agent_id, "role": op.role, "goal": op.goal, "tier": "specialist", "model": model,
            "backstory": f"You are the team's {op.role}. You were added because the team lacked this capability. Write every deliverable you declare and never claim a file you did not write.",
            "tool_ids": list(tools), "skill_ids": list(skills), "max_iterations": 8, "temperature": 0.2,
            "guardrails": [], "knowledge_capsule_ids": [],
        })
        task_id = self._unique({task["id"] for task in node["tasks"]}, f"{agent_id}_task")
        node["tasks"].append({
            "id": task_id, "agent_id": agent_id, "description": op.task_description,
            "expected_output": "A complete deliverable with a summary and the list of files written.",
            "output_schema": schema, "output_schema_json": _deliverable_schema(schema),
            "context_task_ids": [], "expected_artifact_paths": list(op.expected_artifact_paths),
        })
        return AppliedOp(
            op=OpKind.SPAWN_SPECIALIST_AGENT, target_node_id=node["id"], rationale=op.rationale,
            summary=f"Added specialist {op.role} to {node['label']}", modified_nodes=(node["id"],), added_agents=(agent_id,),
        )

    # --- 2. split ----------------------------------------------------------------------------------------------

    def _split(self, doc: Doc, op: SplitOverloaded) -> AppliedOp:
        node = self._node(doc, op.target_node_id, "crew")
        if op.mode == "extract_sandbox":
            return self._extract_sandbox(doc, node, op)
        specialists = [agent for agent in node["agents"] if agent["id"] != node.get("manager_agent_id")]
        if len(node["tasks"]) < 2 or len(specialists) < 2:
            raise MutationError("A crew needs at least two tasks and two specialists to be split")
        halves: list[list[Doc]] = [[], []]
        load = [0, 0]
        for task in sorted(node["tasks"], key=lambda item: -max(1, len(item.get("expected_artifact_paths", ())))):
            index = 0 if load[0] <= load[1] else 1
            halves[index].append(task)
            load[index] += max(1, len(task.get("expected_artifact_paths", ())))
        if not halves[0] or not halves[1]:
            raise MutationError("The crew's work cannot be divided")
        order = {task["id"]: position for position, task in enumerate(node["tasks"])}
        manager = next((agent for agent in node["agents"] if agent["id"] == node.get("manager_agent_id")), None)
        ids = [self._unique({n["id"] for n in doc["nodes"]}, f"{node['id']}_part{i + 1}") for i in range(2)]
        parts: list[Doc] = []
        for index, (part_id, tasks) in enumerate(zip(ids, halves)):
            tasks.sort(key=lambda item: order[item["id"]])
            used = {task["agent_id"] for task in tasks}
            kept = {task["id"] for task in tasks}
            part = copy.deepcopy(node)
            part["id"], part["label"] = part_id, f"{node['label']} · part {'AB'[index]}"
            part["tasks"] = [{**task, "context_task_ids": [ref for ref in task.get("context_task_ids", ()) if ref in kept]} for task in tasks]
            part["agents"] = [agent for agent in node["agents"] if agent["id"] in used or (manager is not None and agent["id"] == manager["id"])]
            part["expected_artifact_paths"] = list(node.get("expected_artifact_paths", ())) if index == 1 else []
            parts.append(part)
        removed = self._detach(doc, node["id"])
        predecessors = [edge for edge in removed if edge["target"] == node["id"]]
        successors = [edge for edge in removed if edge["source"] == node["id"]]
        position = doc["nodes"].index(node)
        doc["nodes"][position:position + 1] = parts
        parallel = self._require_joinable(doc, [edge["target"] for edge in successors])
        for edge in predecessors:
            for part_id in (ids if parallel else ids[:1]):
                doc["edges"].append({"source": edge["source"], "target": part_id, "route": edge.get("route"), "loop_back": False})
        if parallel:
            for edge in successors:
                doc["edges"] += [{"source": part_id, "target": edge["target"], "route": None, "loop_back": False} for part_id in ids]
                self._node(doc, edge["target"])["join"] = "all"
        else:
            doc["edges"].append({"source": ids[0], "target": ids[1], "route": None, "loop_back": False})
            doc["edges"] += [{"source": ids[1], "target": edge["target"], "route": edge.get("route"), "loop_back": False} for edge in successors]
        self._retarget_gate(doc, node["id"], ids)
        for edge in doc["edges"]:
            if edge.get("loop_back") and edge["target"] == node["id"]:
                edge["target"] = ids[0]
        return AppliedOp(
            op=OpKind.SPLIT_OVERLOADED_CREW_OR_SANDBOX, target_node_id=node["id"], rationale=op.rationale,
            summary=f"Split {node['label']} into two {'parallel' if parallel else 'sequential'} crews",
            added_nodes=tuple(ids), removed_nodes=(node["id"],),
        )

    def _extract_sandbox(self, doc: Doc, node: Doc, op: SplitOverloaded) -> AppliedOp:
        declared = self._declared(node)
        extract = [path for path in (op.extract_paths or tuple(p for p in declared if is_code_or_media(p))) if path in declared]
        if not extract:
            raise MutationError("The crew declares no code or media deliverable to extract into a sandbox")
        node["expected_artifact_paths"] = [path for path in node.get("expected_artifact_paths", ()) if path not in extract]
        for task in node["tasks"]:
            task["expected_artifact_paths"] = [path for path in task.get("expected_artifact_paths", ()) if path not in extract]
        sandbox_id = self._unique({n["id"] for n in doc["nodes"]}, f"{node['id']}_build")
        specialists = [agent for agent in node["agents"] if agent["id"] != node.get("manager_agent_id")]
        coder = specialists[0]["model"] if specialists else node["agents"][0]["model"]
        python_files = [path for path in extract if suffix_of(path) == ".py"]
        checks = [f"test -s {path}" for path in extract]
        if python_files:
            checks.append("python -m compileall -q " + " ".join(python_files))
        doc["nodes"].insert(doc["nodes"].index(node) + 1, {
            "id": sandbox_id, "kind": "sandbox", "label": f"{node['label']} · build & verify", "coder_model": coder,
            "reviewer_model": node["agents"][0]["model"],
            "sandbox_provider": "docker", "max_rounds": 8, "timeout_seconds": 900,
            "coder_instructions": f"Implement and run the deliverables {', '.join(extract)} from the specifications written by {node['label']} in the upstream results. Write each file relative to the working directory, creating folders as needed. Never claim a file exists unless the verification command passes.",
            "reviewer_instructions": "Run the verification, inspect each file for placeholders and confirm it matches the specification.",
            "tool_ids": [], "skill_ids": [], "computer_id": None, "verification_command": " && ".join(checks),
            "consensus_config": {"enabled": False, "models": [], "arbiter_model": "", "min_agreement_threshold": 0.85},
            "join": "any", "expected_artifact_paths": extract, "requires_visual_evidence": False,
        })
        for edge in doc["edges"]:
            if edge["source"] == node["id"] and not edge.get("loop_back"):
                edge["source"] = sandbox_id
        doc["edges"].append({"source": node["id"], "target": sandbox_id, "route": None, "loop_back": False})
        self._add_gate_route(doc, node["id"], sandbox_id)
        return AppliedOp(
            op=OpKind.SPLIT_OVERLOADED_CREW_OR_SANDBOX, target_node_id=node["id"], rationale=op.rationale,
            summary=f"Extracted {len(extract)} code/media deliverable(s) from {node['label']} into a verifying sandbox",
            added_nodes=(sandbox_id,), modified_nodes=(node["id"],),
        )

    @staticmethod
    def _add_gate_route(doc: Doc, origin_id: str, new_id: str) -> None:
        """Give a new node its own rework route on every artifact gate that already reworks ``origin_id``."""
        for gate in (node for node in doc["nodes"] if node["kind"] == "router" and node.get("artifact_gate")):
            origin = next((route for route in gate["routes"] if route.get("value") == origin_id), None)
            if origin is None:
                continue
            name = f"rework_{new_id}"
            if any(route["name"] == name for route in gate["routes"]):
                continue
            gate["routes"].append({**origin, "name": name, "value": new_id})
            doc["edges"].append({"source": gate["id"], "target": new_id, "route": name, "loop_back": True})

    # --- 3. quality critic / consensus -------------------------------------------------------------------------

    def _inject(self, doc: Doc, op: InjectQuality) -> AppliedOp:
        node = self._node(doc, op.target_node_id, "crew", "sandbox")
        mode, models, arbiter = op.mode, list(op.models), op.arbiter_model
        if mode == "consensus":
            pool = list(dict.fromkeys([*models, *self._models]))
            families: dict[str, str] = {}
            for name in pool:
                families.setdefault(name.split("/", 1)[0], name)
            if len(families) < 2:
                mode = "critic"
            else:
                chosen = list(families.values())[:3]
                node["consensus_config"] = {
                    "enabled": True, "models": chosen, "arbiter_model": arbiter or chosen[0], "min_agreement_threshold": 0.85,
                }
                return AppliedOp(
                    op=OpKind.INJECT_QUALITY_CRITIC_OR_CONSENSUS, target_node_id=node["id"], rationale=op.rationale,
                    summary=f"Enabled adversarial consensus on {node['label']} across {len(chosen)} model families",
                    modified_nodes=(node["id"],),
                )
        critic_id = self._unique({n["id"] for n in doc["nodes"]}, f"{node['id']}_critic")
        model = node["agents"][0]["model"] if node["kind"] == "crew" else node["reviewer_model"]
        paths = self._declared(node)
        schema = _schema_name(critic_id)
        agent_id = f"{critic_id}_agent"
        doc["nodes"].insert(doc["nodes"].index(node) + 1, {
            "id": critic_id, "kind": "crew", "label": f"{node['label']} · QA critic", "process": "sequential",
            "agents": [{
                "id": agent_id, "role": "QA Critic", "tier": "specialist", "model": model, "tool_ids": [], "skill_ids": [],
                "goal": f"audit the deliverables of {node['label']} against their declared contract and call out anything shallow, unverified or missing",
                "backstory": "You are a sceptical reviewer. You inspect the upstream results and the declared files, never assume a claim is true, and fail the department when evidence is missing.",
                "max_iterations": 6, "temperature": 0.1, "guardrails": [], "knowledge_capsule_ids": [],
            }],
            "tasks": [{
                "id": f"{critic_id}_task", "agent_id": agent_id,
                "description": f"Audit the upstream results of {node['id']}. Declared deliverables: {', '.join(paths) or 'none'}. Set gate_passed to false when any deliverable is missing, empty or superficial and set failing_department to exactly '{node['id']}'; otherwise use true and an empty string.",
                "expected_output": "A critique saved at the declared path with a pass/fail verdict.",
                "output_schema": schema, "output_schema_json": _deliverable_schema(schema, gate=True),
                "context_task_ids": [], "expected_artifact_paths": [f"qa/{critic_id}_critique.md"],
            }],
            "consensus_config": {"enabled": False, "models": [], "arbiter_model": "", "min_agreement_threshold": 0.85},
            "manager_agent_id": None, "join": "any", "expected_artifact_paths": [], "requires_visual_evidence": False,
        })
        for edge in doc["edges"]:
            if edge["source"] == node["id"] and not edge.get("loop_back"):
                edge["source"] = critic_id
        doc["edges"].append({"source": node["id"], "target": critic_id, "route": None, "loop_back": False})
        return AppliedOp(
            op=OpKind.INJECT_QUALITY_CRITIC_OR_CONSENSUS, target_node_id=node["id"], rationale=op.rationale,
            summary=f"Inserted a QA critic after {node['label']}", added_nodes=(critic_id,), added_agents=(agent_id,),
        )

    # --- 4. prune / merge --------------------------------------------------------------------------------------

    def _prune(self, doc: Doc, op: PruneOrMerge) -> AppliedOp:
        node = self._node(doc, op.target_node_id, "crew", "sandbox")
        if op.agent_id is None:
            return self._prune_node(doc, node, op)
        if node["kind"] != "crew":
            raise MutationError("Only crew nodes contain prunable agents")
        agent = next((item for item in node["agents"] if item["id"] == op.agent_id), None)
        if agent is None:
            raise MutationError(f"Agent {op.agent_id} is not in {node['id']}")
        if agent["id"] == node.get("manager_agent_id"):
            raise MutationError("A department lead cannot be pruned")
        owned = [task for task in node["tasks"] if task["agent_id"] == agent["id"]]
        if op.merge_into_agent_id is not None:
            target = next((item for item in node["agents"] if item["id"] == op.merge_into_agent_id), None)
            if target is None or target["id"] in (agent["id"], node.get("manager_agent_id")):
                raise MutationError("Merge target must be another specialist in the same crew")
            for task in owned:
                task["agent_id"] = target["id"]
            target["goal"] = f"{target['goal']} Also covers: {agent['goal']}"
            target["tool_ids"] = list(dict.fromkeys([*target["tool_ids"], *agent["tool_ids"]]))
            target["skill_ids"] = list(dict.fromkeys([*target["skill_ids"], *agent["skill_ids"]]))
            summary = f"Merged {agent['role']} into {target['role']}"
        else:
            if any(task.get("expected_artifact_paths") for task in owned):
                raise MutationError("The agent owns declared deliverables; merge it into another specialist instead")
            removed_tasks = {task["id"] for task in owned}
            node["tasks"] = [task for task in node["tasks"] if task["id"] not in removed_tasks]
            for task in node["tasks"]:
                task["context_task_ids"] = [ref for ref in task.get("context_task_ids", ()) if ref not in removed_tasks]
            summary = f"Pruned redundant agent {agent['role']}"
        node["agents"] = [item for item in node["agents"] if item["id"] != agent["id"]]
        if not node["tasks"]:
            raise MutationError("Pruning would leave the crew without any task; prune the whole node instead")
        if node.get("manager_agent_id") and len(node["agents"]) < 2:
            raise MutationError("A managed crew needs at least one specialist")
        return AppliedOp(
            op=OpKind.PRUNE_OR_MERGE_REDUNDANT_AGENT, target_node_id=node["id"], rationale=op.rationale, summary=summary,
            modified_nodes=(node["id"],), removed_agents=(agent["id"],),
        )

    def _prune_node(self, doc: Doc, node: Doc, op: PruneOrMerge) -> AppliedOp:
        if self._declared(node):
            raise MutationError("The node owns declared deliverables and cannot be removed")
        loop_targets = {edge["target"] for edge in doc["edges"] if edge.get("loop_back")}
        if node["id"] in loop_targets:
            raise MutationError("The node is a rework target of a quality gate")
        if any(route.get("value") == node["id"] for gate in doc["nodes"] if gate["kind"] == "router" for route in gate["routes"]):
            raise MutationError("A quality gate routes to this node")
        removed = self._detach(doc, node["id"])
        predecessors = [edge for edge in removed if edge["target"] == node["id"]]
        successors = [edge for edge in removed if edge["source"] == node["id"]]
        if not predecessors or not successors:
            raise MutationError("Only nodes between two other nodes can be removed")
        for incoming in predecessors:
            for outgoing in successors:
                doc["edges"].append({"source": incoming["source"], "target": outgoing["target"], "route": incoming.get("route"), "loop_back": False})
        doc["nodes"] = [item for item in doc["nodes"] if item["id"] != node["id"]]
        agents = tuple(agent["id"] for agent in node.get("agents", ()))
        seen: set[tuple[str, str, Any]] = set()
        unique_edges: list[Doc] = []
        for edge in doc["edges"]:
            key = (edge["source"], edge["target"], edge.get("route"))
            if key not in seen:
                seen.add(key)
                unique_edges.append(edge)
        doc["edges"] = unique_edges
        return AppliedOp(
            op=OpKind.PRUNE_OR_MERGE_REDUNDANT_AGENT, target_node_id=node["id"], rationale=op.rationale,
            summary=f"Removed redundant node {node['label']}", removed_nodes=(node["id"],), removed_agents=agents,
        )

    # --- 5. sequential -> parallel -----------------------------------------------------------------------------

    def _rewire(self, doc: Doc, op: RewireParallel) -> AppliedOp:
        node = self._node(doc, op.target_node_id, "crew", "sandbox")
        forward = self._forward(doc)
        parents = [edge for edge in forward if edge["target"] == node["id"]]
        children = [edge for edge in forward if edge["source"] == node["id"]]
        if len(parents) != 1 or len(children) != 1:
            raise MutationError("Only a step in a single-path chain can be parallelised")
        pivot = self._node(doc, parents[0]["source"], "crew", "sandbox")
        join_node = self._node(doc, children[0]["target"], *JOINABLE)
        into_pivot = [edge for edge in forward if edge["target"] == pivot["id"]]
        out_of_pivot = [edge for edge in forward if edge["source"] == pivot["id"]]
        if len(into_pivot) != 1 or len(out_of_pivot) != 1:
            raise MutationError("The preceding step is not part of a single-path chain")
        origin = self._node(doc, into_pivot[0]["source"])
        if origin["kind"] == "router" or into_pivot[0].get("route"):
            raise MutationError("Routed branches cannot be parallelised")
        if self.depends_on(node, pivot):
            raise MutationError(f"{node['label']} depends on the output of {pivot['label']}")
        doc["edges"] = [edge for edge in doc["edges"] if edge != parents[0]]
        doc["edges"].append({"source": origin["id"], "target": node["id"], "route": None, "loop_back": False})
        doc["edges"].append({"source": pivot["id"], "target": join_node["id"], "route": None, "loop_back": False})
        join_node["join"] = "all"
        return AppliedOp(
            op=OpKind.REWIRE_SEQUENTIAL_TO_PARALLEL, target_node_id=node["id"], rationale=op.rationale,
            summary=f"{node['label']} now runs in parallel with {pivot['label']}",
            modified_nodes=(node["id"], join_node["id"]),
        )

    @staticmethod
    def depends_on(node: Doc, upstream: Doc) -> bool:
        """True when ``node`` names ``upstream`` or its deliverables, or refers to upstream results generically."""
        parts = [node["label"]]
        if node["kind"] == "crew":
            parts += [task["description"] for task in node["tasks"]]
            parts += [agent["goal"] for agent in node["agents"]]
        else:
            parts += [node.get("coder_instructions", ""), node.get("reviewer_instructions", "")]
        text = " ".join(parts)
        if DEPENDENCY_WORDS.search(text):
            return True
        names = [upstream["id"], upstream["label"], *TeamTopologyMutator._declared(upstream)]
        return any(name and name.lower() in text.lower() for name in names)

    def find_parallelizable(self, spec: WorkflowSpec) -> list[str]:
        doc: Doc = spec.model_dump(mode="json")
        found: list[str] = []
        for node in doc["nodes"]:
            if node["kind"] not in JOINABLE:
                continue
            try:
                scratch = copy.deepcopy(doc)
                self._rewire(scratch, RewireParallel(target_node_id=node["id"]))
                WorkflowSpec.model_validate(self._finalize(scratch, spec, None, None))
            except (MutationError, ValueError, KeyError):
                continue
            found.append(node["id"])
        return found


def diff_specs(before: WorkflowSpec, after: WorkflowSpec) -> TopologyDiff:
    old = {node.id: node.model_dump(mode="json") for node in before.nodes}
    new = {node.id: node.model_dump(mode="json") for node in after.nodes}
    added = tuple(node_id for node_id in new if node_id not in old)
    removed = tuple(node_id for node_id in old if node_id not in new)
    modified = tuple(node_id for node_id in new if node_id in old and new[node_id] != old[node_id])
    gained: dict[str, tuple[str, ...]] = {}
    lost: dict[str, tuple[str, ...]] = {}
    for node_id in new:
        if new[node_id]["kind"] != "crew":
            continue
        after_agents = {agent["id"]: agent["role"] for agent in new[node_id]["agents"]}
        before_agents = {agent["id"]: agent["role"] for agent in old.get(node_id, {}).get("agents", ())}
        plus = tuple(role for agent_id, role in after_agents.items() if agent_id not in before_agents)
        minus = tuple(role for agent_id, role in before_agents.items() if agent_id not in after_agents)
        if plus:
            gained[node_id] = plus
        if minus:
            lost[node_id] = minus
    for node_id in removed:
        if old[node_id]["kind"] == "crew":
            lost[node_id] = tuple(agent["role"] for agent in old[node_id]["agents"])
    old_edges = {(edge.source, edge.target) for edge in before.edges}
    new_edges = {(edge.source, edge.target) for edge in after.edges}
    return TopologyDiff(
        added_nodes=added, modified_nodes=modified, removed_nodes=removed, added_agents=gained, removed_agents=lost,
        added_edges=tuple(sorted(new_edges - old_edges)), removed_edges=tuple(sorted(old_edges - new_edges)),
    )


__all__ = ["MutationError", "MutationResult", "TeamTopologyMutator", "diff_specs"]
