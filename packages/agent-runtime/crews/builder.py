"""Bidirectional, schema-checked crew definitions for JSONC and YAML."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

import yaml  # type: ignore[import-untyped]
from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, create_model

from nexus_core_schema.models import AgentSpec, CrewNodeSpec, TaskSpec
from agent_skills import SkillLoader, SkillSpec
from crews.converter import LlmCallConverter


def _remove_jsonc_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    quoted = False
    escaped = False
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            output.append(char)
            index += 1
        elif char == "/" and next_char == "/":
            index += 2
            while index < len(source) and source[index] != "\n":
                index += 1
        elif char == "/" and next_char == "*":
            end = source.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated JSONC block comment")
            output.extend("\n" for char in source[index:end + 2] if char == "\n")
            index = end + 2
        else:
            output.append(char)
            index += 1
    if quoted:
        raise ValueError("Unterminated JSON string")
    clean = "".join(output)
    result: list[str] = []
    quoted = False
    escaped = False
    for index, char in enumerate(clean):
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        if char == "," and clean[index + 1:].lstrip().startswith(("}", "]")):
            continue
        result.append(char)
    return "".join(result)


CONTEXT_PLACEHOLDERS = ("input", "nodes")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _task_description(description: str) -> str:
    """Keep only runtime placeholders and always give the agent the request and upstream results."""
    safe = _PLACEHOLDER.sub(lambda match: match.group(0) if match.group(1) in CONTEXT_PLACEHOLDERS else f"({match.group(1)})", description)
    if "{input}" not in safe:
        safe += "\n\nRun request and input:\n{input}"
    if "{nodes}" not in safe:
        safe += "\n\nCompleted upstream results:\n{nodes}"
    return safe


@dataclass(frozen=True)
class BuiltCrew:
    spec: CrewNodeSpec
    crew: Crew


class CrewBuilder:
    def __init__(
        self,
        output_schemas: Mapping[str, type[BaseModel]],
        tools: Mapping[str, BaseTool] | None = None,
        manager_llm: Any | None = None,
        skill_loader: SkillLoader | None = None,
        custom_skill_instructions: Mapping[str, str | SkillSpec] | None = None,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> None:
        if not output_schemas:
            raise ValueError("At least one approved output schema is required")
        self._schemas = dict(output_schemas)
        self._tools = dict(tools or {})
        self._manager_llm = manager_llm
        self._skill_loader = skill_loader or SkillLoader()
        self._custom_skills = dict(custom_skill_instructions or {})
        self._on_progress = on_progress
        self._dynamic_schemas: dict[str, type[BaseModel]] = {}

    def schema_for_task(self, task: TaskSpec) -> type[BaseModel]:
        if task.output_schema_json is None:
            schema = self._schemas.get(task.output_schema)
            if schema is None or not issubclass(schema, BaseModel):
                raise ValueError(f"Unregistered Pydantic output schema: {task.output_schema}")
            return schema
        cached = self._dynamic_schemas.get(task.output_schema)
        if cached is not None:
            return cached
        document = task.output_schema_json
        properties = document.get("properties")
        required = document.get("required", [])
        if document.get("type") != "object" or not isinstance(properties, dict) or not properties or len(properties) > 64:
            raise ValueError("Generated output schema must be a bounded JSON object schema")
        allowed_types: dict[str, Any] = {"string": str, "integer": int, "number": float, "boolean": bool}
        definitions: dict[str, Any] = {}
        for name, definition in properties.items():
            if not isinstance(name, str) or not name.isidentifier() or not isinstance(definition, dict):
                raise ValueError("Generated output schema contains an invalid field")
            field_type = definition.get("type")
            if field_type == "array":
                items = definition.get("items")
                if not isinstance(items, dict):
                    raise ValueError("Generated output arrays must declare scalar item types")
                item_type = allowed_types.get(str(items.get("type")))
                if item_type is None:
                    raise ValueError("Generated output arrays must contain scalar values")
                parsed_type: Any = list.__class_getitem__(item_type)
            else:
                parsed_type = allowed_types.get(str(field_type))
            if parsed_type is None:
                raise ValueError("Generated output schema uses an unsupported scalar type")
            definitions[name] = (parsed_type, ... if name in required else None)
        schema = create_model(task.output_schema, **definitions)
        self._dynamic_schemas[task.output_schema] = schema
        return schema

    def load(self, path: Path) -> CrewNodeSpec:
        if path.stat().st_size > 1_048_576:
            raise ValueError("Crew definition exceeds the 1 MiB limit")
        source = path.read_text(encoding="utf-8")
        if path.suffix in (".jsonc", ".json"):
            data = json.loads(_remove_jsonc_comments(source))
        elif path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(source)
        else:
            raise ValueError("Crew definition must be JSONC or YAML")
        return CrewNodeSpec.model_validate(data)

    def export(self, spec: CrewNodeSpec, path: Path) -> None:
        self._validate_output_schemas(spec)
        data = spec.model_dump(mode="json")
        if path.suffix in (".jsonc", ".json"):
            source = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        elif path.suffix in (".yaml", ".yml"):
            source = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        else:
            raise ValueError("Crew definition must be JSONC or YAML")
        path.write_text(source, encoding="utf-8")

    def _validate_output_schemas(self, spec: CrewNodeSpec) -> None:
        for task in spec.tasks:
            schema = self.schema_for_task(task)
            if schema is None or not issubclass(schema, BaseModel):
                raise ValueError(f"Unregistered Pydantic output schema: {task.output_schema}")

    def build(
        self,
        spec: CrewNodeSpec,
        model_overrides: Mapping[str, Any] | None = None,
        task_preambles: Mapping[str, str] | None = None,
    ) -> BuiltCrew:
        """Build a native crew. ``task_preambles`` appends runtime instructions (artifact contracts) per task."""
        self._validate_output_schemas(spec)
        resolved_models = dict(model_overrides or {})
        if spec.process == "hierarchical" and self._manager_llm is None and spec.manager_agent_id is None:
            raise ValueError("Hierarchical crews require a manager agent or an approved manager model")
        agents: dict[str, Agent] = {}
        manager: Agent | None = None
        def progress_for(role: str) -> Callable[[Any], None]:
            def callback(step: Any) -> None:
                action = getattr(step, "action", step)
                note = getattr(action, "thought", "")
                final = getattr(action, "return_values", {})
                if isinstance(final, dict) and isinstance(final.get("output"), str):
                    answer = final["output"]
                    try:
                        parsed = json.loads(answer)
                    except json.JSONDecodeError:
                        note = answer
                    else:
                        if isinstance(parsed, dict):
                            value = next((parsed[key] for key in ("summary", "answer", "result") if isinstance(parsed.get(key), (str, int, float))), None)
                            if value is not None:
                                note = str(value)
                        elif isinstance(parsed, (str, int, float)):
                            note = str(parsed)
                if self._on_progress is not None and isinstance(note, str) and note.strip():
                    self._on_progress(spec.id, role, note.strip()[:1200])
            return callback
        for agent_spec in spec.agents:
            if agent_spec.id == spec.manager_agent_id:
                manager = Agent(
                    role=agent_spec.role,
                    goal=agent_spec.goal,
                    backstory=(agent_spec.backstory or agent_spec.role)
                    + "\n\nYou lead this department: split the work between your specialists, review each deliverable "
                    "against its artifact contract, and send back work that misses it."
                    + ("\n\nGuardrails:\n" + "\n".join(f"- {rule}" for rule in agent_spec.guardrails) if agent_spec.guardrails else ""),
                    llm=resolved_models.get(agent_spec.model, agent_spec.model),
                    tools=[],
                    max_iter=agent_spec.max_iterations,
                    allow_delegation=True,
                    verbose=False,
                )
                continue
            unknown_skills = set(agent_spec.skill_ids) - set(self._skill_loader._skills) - self._custom_skills.keys()
            if unknown_skills:
                raise ValueError(f"Unknown skill IDs: {sorted(unknown_skills)}")
            task_text = " ".join(task.description for task in spec.tasks if task.agent_id == agent_spec.id)
            assigned_skills: list[str] = []
            effective_tools = list(agent_spec.tool_ids)
            if "sandbox_shell" in effective_tools:
                effective_tools.extend(tool_id for tool_id in ("view_file_numbered", "surgical_file_edit", "fast_workspace_search", "start_background_process", "get_process_logs", "stop_process", "list_running_processes") if tool_id in self._tools and tool_id not in effective_tools)
            for slug in agent_spec.skill_ids:
                skill = self._custom_skills.get(slug, self._skill_loader._skills.get(slug))
                if isinstance(skill, SkillSpec):
                    assigned_skills.append(skill.body)
                    effective_tools.extend((*skill.required_tools, *skill.required_builtin_tools))
                elif isinstance(skill, str):
                    assigned_skills.append(skill)
            for matched_skill in self._skill_loader.match(task_text):
                if matched_skill.slug not in agent_spec.skill_ids:
                    assigned_skills.append(matched_skill.body)
                    effective_tools.extend(tool for tool in (*matched_skill.required_tools, *matched_skill.required_builtin_tools) if tool in self._tools)
            effective_tools = list(dict.fromkeys(effective_tools))
            missing = set(effective_tools) - self._tools.keys()
            if missing:
                raise ValueError(f"Unknown or disabled tool IDs required by agent skills: {sorted(missing)}")
            agents[agent_spec.id] = Agent(
                role=agent_spec.role,
                goal=agent_spec.goal,
                backstory=(agent_spec.backstory or agent_spec.role)
                + ("\n\nAssigned skill instructions:\n" + "\n\n".join(assigned_skills) if assigned_skills else "")
                + "\n\nKeep progress notes user-facing and brief: explain the next action and what it checks. Do not include private reasoning or secrets."
                + ("\n\nGuardrails:\n" + "\n".join(f"- {rule}" for rule in agent_spec.guardrails) if agent_spec.guardrails else ""),
                llm=resolved_models.get(agent_spec.model, agent_spec.model),
                tools=[self._tools[tool_id] for tool_id in effective_tools],
                max_iter=agent_spec.max_iterations,
                allow_delegation=False,
                step_callback=progress_for(agent_spec.role),
                verbose=False,
            )
        tasks: dict[str, Task] = {}
        for task_spec in spec.tasks:
            missing_context = set(task_spec.context_task_ids) - tasks.keys()
            if missing_context:
                raise ValueError("Task context must reference earlier tasks")
            preamble = (task_preambles or {}).get(task_spec.id, "")
            tasks[task_spec.id] = Task(
                description=_task_description(task_spec.description + (f"\n\n{preamble}" if preamble else "")),
                expected_output=task_spec.expected_output,
                agent=agents[task_spec.agent_id],
                context=[tasks[task_id] for task_id in task_spec.context_task_ids],
                output_pydantic=self.schema_for_task(task_spec),
                converter_cls=LlmCallConverter,
            )
        kwargs: dict[str, Any] = {
            "agents": list(agents.values()),
            "tasks": list(tasks.values()),
            "process": Process(spec.process),
            "verbose": False,
        }
        if manager is not None:
            kwargs["manager_agent"] = manager
        elif self._manager_llm is not None and spec.process == "hierarchical":
            kwargs["manager_llm"] = self._manager_llm
        return BuiltCrew(spec=spec, crew=Crew(**kwargs))

    def from_crew(self, crew: Crew, *, node_id: str, label: str) -> CrewNodeSpec:
        agent_ids = {id(agent): f"agent_{index}" for index, agent in enumerate(crew.agents, 1)}
        task_ids = {id(task): f"task_{index}" for index, task in enumerate(crew.tasks, 1)}
        agents = tuple(
            AgentSpec(
                id=agent_ids[id(agent)],
                role=agent.role,
                goal=agent.goal,
                backstory=agent.backstory,
                model=str(getattr(agent.llm, "model", agent.llm)),
                tool_ids=tuple(tool.name for tool in (agent.tools or [])),
                max_iterations=agent.max_iter,
            )
            for agent in crew.agents
        )
        tasks: list[TaskSpec] = []
        for task in crew.tasks:
            schema = task.output_pydantic
            if schema is None or schema.__name__ not in self._schemas or self._schemas[schema.__name__] is not schema:
                raise ValueError("Crew task lacks a registered Pydantic output schema")
            if task.agent is None or id(task.agent) not in agent_ids:
                raise ValueError("Crew task references an unknown agent")
            context_tasks = task.context if isinstance(task.context, list) else []
            if any(id(context) not in task_ids for context in context_tasks):
                raise ValueError("Crew task context references an unknown task")
            tasks.append(TaskSpec(
                id=task_ids[id(task)],
                agent_id=agent_ids[id(task.agent)],
                description=task.description,
                expected_output=task.expected_output,
                output_schema=schema.__name__,
                context_task_ids=tuple(task_ids[id(context)] for context in context_tasks),
            ))
        process: Literal["sequential", "hierarchical"] = (
            "hierarchical" if crew.process == Process.hierarchical else "sequential"
        )
        return CrewNodeSpec(
            id=node_id,
            label=label,
            agents=agents,
            tasks=tuple(tasks),
            process=process,
        )
