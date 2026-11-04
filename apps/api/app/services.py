"""Control-plane service wiring around the existing scoped runtime packages."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Protocol, cast
from uuid import UUID, uuid4

from autogen_core.models import ChatCompletionClient
from crewai import LLM
from pydantic import BaseModel, create_model
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.billing.plans import enforce_monthly_sandbox_quota
from app.learning import save_capsule
from app.models import AgentSkill, AuditLog, KnowledgeBase, KnowledgeCapsule, LearningPolicy as LearningPolicyRow, ModelCredential, SandboxComputer, TenantBudget, TransferApplicationLog, TransferCircuitBreaker, Workflow, WorkflowRun, WorkspaceBuiltinTool
from app.models.connection import create_runtime_engine
from app.models.gateway_store import SqlGatewayStore
from app.models.scope import scoped_session
from nexusgen_bridge.sandbox_team import NexusGenSandboxRunner
from bots.gateway import GatewayBotResponder
from bots.runner import BotRunner
from callbacks.event_bus import RuntimeEventEmitter
from checkpoints.approval import ActionIntent, ApprovalCoordinator
from checkpoints.store import CheckpointStore
from crews.builder import CrewBuilder
from flows.compiler import CompiledWorkflow, FlowCompiler
from flows.state import WorkflowState
from nexus_computer_sandbox import ComputerAccess, ComputerSandboxSupervisor, DockerSandboxProvider
from nexus_core_schema.models import CrewNodeSpec, KnowledgeCapsuleSpec, PersistentBotSpec, PropagationScope, SensitivityLevel, RAGNodeSpec, RuntimeEventType, WorkflowSpec
from nexus_core_schema.artifacts import artifact_directory
from nexus_core_schema.template_outputs import BUILTIN_OUTPUT_SCHEMAS
from nexus_model_gateway import CredentialCipher, LiteLLMEmbeddingRouter, LiteLLMRouter, ModelRate, UsageRecord
from nexus_model_gateway.router import price_for
from nexus_model_gateway.router import GatewayRequest
from nexus_model_gateway.router import Provider
from nexus_model_gateway.media import MediaCredential, MediaGatewayService
from nexus_rag_engine import KnowledgeScope, MultiTenantRAGEngine
from learning_transfer.negative_transfer_detector import DetectorConfig, TransferObservation, score_transfer_pair
from learning_transfer.scope_firewall import AgentLearningContext, LearningPolicy, ScopeFirewall
from nexus_builtin_tools import BuiltinToolRegistry, TOOLS, ToolContext
from team_evolution import DYNAMIC_TEAM_TOOL_ID, DynamicSpawner, DynamicTeamMutatorTool, SpawnRecord, TeamTopologyMutator
from agent_skills import SkillLoader, SkillSpec
from nexus_kernel import Kernel
from nexus_plugins import boot_default
from nexus_plugins import seams
from nexus_plugins.support.llm_service import LlmService, load_model_rates
from nexus_plugins.support.tool_service import ToolRegistryService


class TaskDispatcher(Protocol):
    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def workflow(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None: ...
    async def bot_turn(self, tenant_id: UUID, workspace_id: UUID, bot_id: UUID, thread_id: UUID, content: str) -> None: ...
    async def routine(self, tenant_id: UUID, workspace_id: UUID, routine_run_id: UUID) -> None: ...


class NexusTextResult(BaseModel):
    result: str


def _output_schemas() -> dict[str, type[BaseModel]]:
    source = os.environ.get("NEXUS_OUTPUT_SCHEMAS_JSON", "{}")
    if len(source) > 65_536:
        raise ValueError("Structured output configuration is too large")
    raw = json.loads(source)
    if not isinstance(raw, dict):
        raise ValueError("Structured output configuration must be an object")
    result: dict[str, type[BaseModel]] = {"NexusTextResult": NexusTextResult, **BUILTIN_OUTPUT_SCHEMAS}
    types: dict[str, Any] = {"string": str, "integer": int, "number": float, "boolean": bool}
    for name, fields in raw.items():
        if not isinstance(name, str) or not name.isidentifier() or not isinstance(fields, dict) or not fields:
            raise ValueError("Structured output model is invalid")
        definitions: dict[str, Any] = {}
        for field_name, kind in fields.items():
            if not isinstance(field_name, str) or not field_name.isidentifier() or not isinstance(kind, str) or kind not in types:
                raise ValueError("Structured output field is invalid")
            definitions[field_name] = (types[kind], ...)
        result[name] = create_model(name, **definitions)
    return result


@dataclass
class AppServices:
    """What the routers and workers use. The long-lived parts (connections, sandbox, model access, tools, checkpoints)
    are services published by plugins; see `nexus_plugins`. Built directly, it falls back to plain defaults."""

    engine: AsyncEngine
    redis: Redis
    qdrant: AsyncQdrantClient
    sandbox: ComputerSandboxSupervisor
    sandbox_runner: NexusGenSandboxRunner
    dispatcher: TaskDispatcher
    output_schemas: dict[str, type[BaseModel]] = field(default_factory=_output_schemas)
    llm_service: LlmService | None = None
    tools: ToolRegistryService = field(default_factory=ToolRegistryService)
    checkpoint_store: CheckpointStore | None = None
    kernel: Kernel | None = None

    def __post_init__(self) -> None:
        if self.llm_service is None:
            self.llm_service = LlmService(self.engine, load_model_rates())
        if self.checkpoint_store is None:
            self.checkpoint_store = CheckpointStore(self.engine, self.redis)

    @property
    def llm(self) -> LlmService:
        assert self.llm_service is not None
        return self.llm_service

    @property
    def checkpoints(self) -> CheckpointStore:
        assert self.checkpoint_store is not None
        return self.checkpoint_store

    @property
    def model_rates(self) -> dict[tuple[Provider, str], ModelRate]:
        return self.llm.rates

    @property
    def workspace_tools(self) -> dict[tuple[UUID, UUID], dict[str, Any]]:
        return self.tools.workspace_tools

    @property
    def run_tool_registries(self) -> dict[tuple[UUID, UUID, UUID], BuiltinToolRegistry]:
        return self.tools.run_registries

    async def shutdown(self) -> None:
        """Close what this object owns: the plugin kernel and everything it opened, or the three connections when built by hand."""
        if self.kernel is not None:
            await self.kernel.close()
            return
        await self.redis.aclose()
        await self.qdrant.close()
        await self.engine.dispose()

    def _store(self) -> SqlGatewayStore:
        return self.llm.store()

    def gateway(self) -> LiteLLMRouter:
        return self.llm.gateway()

    def embeddings(self) -> LiteLLMEmbeddingRouter:
        return self.llm.embeddings()

    def rag(self) -> MultiTenantRAGEngine:
        return MultiTenantRAGEngine(self.engine, self.qdrant, self.embeddings())

    def crew_builder(self, tenant_id: UUID | None = None, workspace_id: UUID | None = None) -> CrewBuilder:
        tools = self.workspace_tools.get((tenant_id, workspace_id), {}) if tenant_id is not None and workspace_id is not None else {}
        return CrewBuilder(self.output_schemas, tools, skill_loader=SkillLoader())

    async def _runtime_crew_builder(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, extra_tools: dict[str, Any] | None = None) -> CrewBuilder:
        async with scoped_session(self.engine, tenant_id, workspace_id) as session:
            skill_rows = (await session.scalars(select(AgentSkill))).all()
            disabled = set((await session.scalars(select(WorkspaceBuiltinTool.tool_id).where(WorkspaceBuiltinTool.enabled.is_(False)))).all())
            knowledge_ids = tuple((await session.scalars(select(KnowledgeBase.id))).all())
        custom_skills = {row.slug: SkillSpec.from_markdown(row.content) for row in skill_rows}
        enabled = frozenset(item.id for item in TOOLS if item.id not in disabled)
        artifact_root = artifact_directory(tenant_id, workspace_id, run_id)
        artifact_root.mkdir(parents=True, exist_ok=True)

        async def rag_query(query: str) -> Any:
            from nexus_rag_engine import KnowledgeScope
            results: list[dict[str, Any]] = []
            for knowledge_id in knowledge_ids:
                hits = await self.rag().retrieve(KnowledgeScope(tenant_id, workspace_id, knowledge_id), query)
                results.extend({"document_id": str(hit.document_id), "filename": hit.filename, "text": hit.text, "score": hit.score} for hit in hits)
            return sorted(results, key=lambda result: result["score"], reverse=True)[:12]

        async def shell(command: str, timeout: int) -> Any:
            emitter = RuntimeEventEmitter(self.redis, tenant_id, workspace_id, run_id)
            async def sink(stream: str, content: str) -> None:
                await emitter.emit(RuntimeEventType.SANDBOX_TERMINAL_OUTPUT, {"stream": stream, "content": content})
            async with scoped_session(self.engine, tenant_id, workspace_id) as session:
                computer = await session.scalar(select(SandboxComputer).where(
                    SandboxComputer.run_id == run_id, SandboxComputer.status == "running",
                ))
            if computer is None:
                raise RuntimeError("No isolated computer is assigned to this run")
            result = await self.sandbox.execute_shell(
                ComputerAccess(tenant_id, workspace_id, run_id=run_id),
                computer.id, command, timeout, sink,
            )
            return {"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr}

        async def boundary_guard(kind: str, description: str) -> None:
            if kind != "external_action":
                raise PermissionError("This tool requested an unsupported approval boundary")
            coordinator = self.approvals(tenant_id, workspace_id, UUID(int=0))
            await coordinator.computer_guard(ComputerAccess(tenant_id, workspace_id, run_id=run_id), kind, description)

        async def media(kind: str, payload: dict[str, Any]) -> Any:
            preferred = ("shopaikey", "openai", "google_gemini") if kind in {"image", "video"} else ("shopaikey", "openai", "elevenlabs")
            async with scoped_session(self.engine, tenant_id, workspace_id) as session:
                rows = (await session.scalars(select(ModelCredential).where(
                    ModelCredential.status == "connected", ModelCredential.preset_id.in_(preferred),
                ).order_by(ModelCredential.is_default.desc(), ModelCredential.created_at.desc()))).all()
            row = next((item for preset in preferred for item in rows if item.preset_id == preset), None)
            if row is not None:
                fields = CredentialCipher.decode_fields(self._store()._cipher.decrypt(
                    row.encrypted_key, tenant_id, workspace_id, row.provider,
                ))
                credential = MediaCredential(row.preset_id, fields.get("api_key", ""),
                    row.base_url or ("https://api.shopaikey.com/v1" if row.preset_id == "shopaikey" else "https://api.openai.com/v1"),
                    row.default_models, row.settings)
            else:
                key = os.environ.get("NEXUS_SHOPAIKEY_API_KEY") or os.environ.get("NEXUS_OPENAI_API_KEY")
                if not key:
                    raise RuntimeError("No workspace media credential is configured")
                preset = "shopaikey" if os.environ.get("NEXUS_SHOPAIKEY_API_KEY") else "openai"
                credential = MediaCredential(preset, key,
                    "https://api.shopaikey.com/v1" if preset == "shopaikey" else "https://api.openai.com/v1")
            return await MediaGatewayService(credential, artifact_root).generate(kind, payload)

        async def workflow_delegate(workflow_id: str, inputs: dict[str, Any]) -> Any:
            target_id = UUID(workflow_id)
            delegated_id = uuid4()
            async with scoped_session(self.engine, tenant_id, workspace_id) as session:
                target = await session.get(Workflow, target_id)
                if target is None:
                    raise LookupError("Delegated workflow is unavailable in this workspace")
                session.add(WorkflowRun(
                    id=delegated_id, tenant_id=tenant_id, workspace_id=workspace_id,
                    workflow_id=target_id, status="queued", input_data=inputs,
                ))
            await self.dispatcher.workflow(tenant_id, workspace_id, delegated_id)
            return {"run_id": str(delegated_id), "workflow_id": workflow_id, "status": "queued"}

        credentials = {name: os.environ[key] for name, key in (("serper", "NEXUS_SERPER_API_KEY"), ("tavily", "NEXUS_TAVILY_API_KEY")) if os.environ.get(key)}
        registry = BuiltinToolRegistry(ToolContext(
            str(tenant_id), str(workspace_id), str(run_id), artifact_root, enabled,
            rag_query=rag_query, shell=shell, media=media, workflow_delegate=workflow_delegate,
            search_credentials=credentials, boundary_guard=boundary_guard,
        ))
        self.tools.remember_run(tenant_id, workspace_id, run_id, registry)
        tool_map = {tool.tool_id: tool for tool in registry.nexusai_tools()}
        tool_map.update(self.workspace_tools.get((tenant_id, workspace_id), {}))
        tool_map.update(extra_tools or {})
        return CrewBuilder(self.output_schemas, tool_map, skill_loader=SkillLoader(), custom_skill_instructions=custom_skills)

    async def tenant_model_client(self, tenant_id: UUID, workspace_id: UUID, model: str) -> LLM | None:
        return await self.llm.nexusai_client(tenant_id, workspace_id, model)

    def bot_runner(self, tenant_id: UUID, workspace_id: UUID, actor_id: UUID | None = None) -> BotRunner:
        async def boundary_requester(run_id: UUID, intent: ActionIntent) -> UUID | None:
            coordinator = self.approvals(tenant_id, workspace_id, actor_id or UUID(int=0))
            return await coordinator.pause_routine_for_action(run_id, intent)

        async def respond(bot: PersistentBotSpec, messages: tuple[tuple[str, str], ...]) -> str:
            await self._runtime_crew_builder(tenant_id, workspace_id, bot.id)
            registry = self.run_tool_registries[(tenant_id, workspace_id, bot.id)]
            async with scoped_session(self.engine, tenant_id, workspace_id) as session:
                workflows = (await session.scalars(select(Workflow).order_by(Workflow.name))).all()

            async def execute(tool_id: str, arguments: dict[str, Any]) -> Any:
                if tool_id not in bot.tool_ids:
                    raise PermissionError("Bot has not been assigned this tool")
                result = await registry.run(tool_id, arguments)
                if isinstance(result, dict) and isinstance(result.get("artifact"), str):
                    result = {**result, "download_url": f"/api/v1/bots/{bot.id}/artifacts/{result['artifact']}"}
                return result

            return await GatewayBotResponder(self.gateway(), tool_executor=execute,
                available_workflows={row.name: str(row.id) for row in workflows})(bot, messages)

        return BotRunner(
            self.engine, self.redis, tenant_id, workspace_id,
            respond, self.sandbox_runner,
            self.crew_builder(tenant_id, workspace_id), boundary_requester,
        )

    async def compiled_workflow(
        self, tenant_id: UUID, workspace_id: UUID, run_id: UUID,
        input_data: dict[str, Any] | None = None,
    ) -> CompiledWorkflow:
        from sqlalchemy import select

        async with scoped_session(self.engine, tenant_id, workspace_id) as session:
            run = await session.get(WorkflowRun, run_id)
            if run is None:
                raise LookupError("Workflow run is not visible in this workspace")
            row = await session.scalar(select(Workflow).where(Workflow.id == run.workflow_id))
            if row is None:
                raise LookupError("Workflow is not visible in this workspace")
            spec = WorkflowSpec.model_validate(row.spec)

        learning_trials: dict[tuple[UUID, str], list[tuple[UUID, UUID, str, str, str]]] = {}

        async def rag_handler(node: RAGNodeSpec, state: WorkflowState) -> dict[str, Any]:
            query_input = next((
                value for key in ("query", "question", "priority_context", "task", "request")
                if isinstance((value := state.input_data.get(key)), str) and value.strip()
            ), "")
            query = node.query_template.replace("{input}", query_input)
            hits = await self.rag().retrieve(
                KnowledgeScope(tenant_id, workspace_id, node.knowledge_base_id), query, limit=node.top_k,
            )
            return {"hits": [
                {"document_id": str(hit.document_id), "text": hit.text, "score": hit.score, "filename": hit.filename}
                for hit in hits
            ]}

        async def usage_handler(
            state: WorkflowState, agent_name: str, model_name: str,
            prompt_tokens: int, completion_tokens: int, sandbox_seconds: float,
        ) -> None:
            provider_name, separator, provider_model = model_name.partition("/")
            if not separator:
                provider_name, provider_model = "openai", model_name
            if provider_name not in {"openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm", "groq", "mistral", "together_ai"}:
                raise ValueError("Workflow usage has an unsupported model provider")
            store = self._store()
            workspace_credential = await store.resolve_default_credential(
                state.tenant_id, state.workspace_id, cast(Provider, provider_name),
            )
            rate, billing_mode = price_for(self.model_rates, cast(Provider, provider_name), provider_model, workspace_credential)
            cost = rate.cost(prompt_tokens, completion_tokens, Decimal("1"))
            record = UsageRecord(
                tenant_id=state.tenant_id, workspace_id=state.workspace_id,
                workflow_id=state.workflow_id, run_id=state.run_id, agent_name=agent_name,
                provider=cast(Provider, provider_name), model=provider_model,
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_cost_usd=cost,
                latency_ms=0, sandbox_compute_seconds=Decimal(str(sandbox_seconds)),
                billing_mode=billing_mode,
            )
            managed_charge = workspace_credential is None and cost > 0
            if managed_charge:
                await store.reserve(state.tenant_id, state.workspace_id, cost)
            try:
                await store.finalize(cost if managed_charge else Decimal("0"), record, managed_charge)
            except BaseException:
                if managed_charge:
                    await store.release(state.tenant_id, state.workspace_id, cost)
                raise

        async def learning_context_handler(state: WorkflowState, node: Any) -> dict[str, str]:
            edges = [edge for edge in spec.learning_edges if any(agent.id == edge.target_agent_id for agent in node.agents)]
            attached_ids = {capsule_id for agent in node.agents for capsule_id in agent.knowledge_capsule_ids}
            if not edges and not attached_ids:
                return {}
            source_ids = {edge.source_agent_id for edge in edges}
            target_ids = {edge.target_agent_id for edge in edges}
            async with scoped_session(self.engine, tenant_id, workspace_id) as session:
                capsules = (await session.scalars(select(KnowledgeCapsule).where(
                    KnowledgeCapsule.status == "active",
                    or_(
                        KnowledgeCapsule.source_agent_id.in_(source_ids) if source_ids else false(),
                        KnowledgeCapsule.capsule_id.in_(attached_ids) if attached_ids else false(),
                    ),
                ))).all()
                policies = (await session.scalars(select(LearningPolicyRow).where(
                    LearningPolicyRow.source_agent_id.in_(source_ids),
                    LearningPolicyRow.target_agent_id.in_(target_ids), LearningPolicyRow.allowed.is_(True),
                ))).all()
                blocked_direct = set((await session.scalars(select(TransferCircuitBreaker.capsule_id).where(
                    TransferCircuitBreaker.capsule_id.in_(attached_ids),
                    TransferCircuitBreaker.active.is_(True),
                ))).all()) if attached_ids else set()
                historical_negative = set((await session.scalars(select(TransferApplicationLog.capsule_id).where(
                    TransferApplicationLog.capsule_id.in_(attached_ids),
                    TransferApplicationLog.condition == "treatment",
                    TransferApplicationLog.tis_score < -0.15,
                ))).all()) if attached_ids else set()
            policies_by_pair = {(item.source_agent_id, item.target_agent_id): LearningPolicy(
                source_agent_id=item.source_agent_id, target_agent_id=item.target_agent_id,
                scope=PropagationScope(item.propagation_scope), allow_heuristics=item.allow_heuristics,
                allow_code_patterns=item.allow_code_patterns,
                require_human_approval=item.require_human_approval, allowed=item.allowed,
            ) for item in policies}
            firewall = ScopeFirewall(top_k=3)
            result: dict[str, str] = {}
            for target_spec in node.agents:
                target_edges = [edge for edge in edges if edge.target_agent_id == target_spec.id]
                task_text = " ".join(task.description for task in node.tasks if task.agent_id == target_spec.id)
                target = AgentLearningContext(
                    agent_id=target_spec.id, domain_tags=tuple(target_spec.role.lower().split()),
                    task_description=task_text, tenant_id=tenant_id, workspace_id=workspace_id,
                )
                decisions = []
                eligible_rows: list[tuple[Any, Any]] = []
                for edge in target_edges:
                    policy = policies_by_pair.get((edge.source_agent_id, edge.target_agent_id))
                    if policy is None or (policy.scope != edge.scope
                            or policy.allow_heuristics != edge.allow_heuristics
                            or policy.allow_code_patterns != edge.allow_code_patterns
                            or policy.require_human_approval != edge.require_human_approval):
                        continue
                    for capsule_row in capsules:
                        if capsule_row.source_agent_id != edge.source_agent_id:
                            continue
                        eligible_rows.append((capsule_row, edge))
                        capsule = KnowledgeCapsuleSpec(
                            tenant_id=capsule_row.tenant_id, workspace_id=capsule_row.workspace_id,
                            capsule_id=capsule_row.capsule_id, source_agent_id=capsule_row.source_agent_id,
                            source_role=capsule_row.source_role, source_domain_tags=tuple(capsule_row.source_domain_tags),
                            trigger_preconditions=capsule_row.trigger_preconditions,
                            distilled_heuristic=capsule_row.distilled_heuristic,
                            prohibited_contexts=tuple(capsule_row.prohibited_contexts),
                            propagation_scope=PropagationScope(capsule_row.propagation_scope),
                            sensitivity_level=SensitivityLevel(capsule_row.sensitivity_level),
                            source_workflow_id=capsule_row.source_workflow_id,
                            source_crew_id=capsule_row.source_crew_id, confidence=capsule_row.confidence,
                        )
                        decision = firewall.authorize(
                            capsule, target, policy,
                            same_crew=capsule_row.source_crew_id == node.id,
                            same_workflow=capsule_row.source_workflow_id == state.workflow_id,
                        )
                        if decision.allowed:
                            decisions.append(decision)
                decisions.sort(key=lambda item: item.compatibility, reverse=True)
                selected_capsules = {item.capsule.capsule_id for item in decisions[:firewall.top_k] if item.capsule is not None}
                trials = learning_trials.setdefault((state.run_id, target_spec.id), [])
                for capsule_row, _edge in eligible_rows:
                    pair = (capsule_row.id, capsule_row.capsule_id, capsule_row.source_agent_id, target_spec.id)
                    if not any(item[:2] == pair[:2] and item[3] == pair[3] for item in trials):
                        trials.append((*pair[:2], pair[2], pair[3], "treatment" if capsule_row.capsule_id in selected_capsules else "baseline"))
                learned = [
                        f"- [{item.capsule.source_role}] {item.capsule.distilled_heuristic}"
                        for item in decisions[:firewall.top_k] if item.capsule is not None
                    ]
                for capsule_row in capsules:
                    if capsule_row.capsule_id not in target_spec.knowledge_capsule_ids:
                        continue
                    if (capsule_row.capsule_id in blocked_direct or capsule_row.capsule_id in historical_negative
                            or capsule_row.propagation_scope != PropagationScope.WORKSPACE_VERIFIED.value
                            or capsule_row.confidence < 0.85):
                        continue
                    learned.append(f"- [Verified workspace capsule · {capsule_row.source_role}] {capsule_row.distilled_heuristic}")
                if learned:
                    result[target_spec.id] = "\n".join(learned[:firewall.top_k])
            return result

        async def learning_outcome_handler(
            state: WorkflowState, node: Any, success: bool, token_count: int, latency_ms: int,
        ) -> None:
            trial_groups = [(key, values) for key, values in learning_trials.items() if key[0] == state.run_id and any(agent.id == key[1] for agent in node.agents)]
            if not trial_groups:
                return
            negative_events: list[dict[str, Any]] = []
            async with scoped_session(self.engine, tenant_id, workspace_id) as session:
                for (run_id, target_agent_id), trials in trial_groups:
                    for capsule_row_id, capsule_id, source_agent_id, target_id, condition in trials:
                        new_log = TransferApplicationLog(
                            id=uuid4(), tenant_id=tenant_id, workspace_id=workspace_id,
                            capsule_id=capsule_row_id, run_id=run_id, source_agent_id=source_agent_id,
                            target_agent_id=target_id, condition=condition, success=success,
                            retry_and_error_turns=0, human_approval_rejected=False,
                            token_count=token_count, latency_ms=latency_ms, target_domain_tags=[],
                        )
                        session.add(new_log)
                        observations = (await session.scalars(select(TransferApplicationLog).where(
                            TransferApplicationLog.capsule_id == capsule_row_id,
                            TransferApplicationLog.target_agent_id == target_id,
                        ))).all()
                        def to_metric(item: TransferApplicationLog) -> TransferObservation:
                            return TransferObservation(
                            success=item.success, retry_and_error_turns=item.retry_and_error_turns,
                            human_approval_rejected=item.human_approval_rejected,
                            token_count=item.token_count, latency_ms=item.latency_ms,
                            )
                        baseline = tuple(to_metric(item) for item in observations if item.condition == "baseline")
                        treatment = tuple(to_metric(item) for item in observations if item.condition == "treatment")
                        decision = score_transfer_pair(capsule_id, target_id, baseline, treatment, DetectorConfig(
                            threshold=float(os.environ.get("NEXUS_TRANSFER_NEGATIVE_THRESHOLD", "0.15")),
                            minimum_applications=int(os.environ.get("NEXUS_TRANSFER_MIN_APPLICATIONS", "5")),
                        ))
                        new_log.tis_score = decision.impact.score
                        if not decision.negative_transfer:
                            continue
                        capsule = await session.get(KnowledgeCapsule, capsule_row_id, with_for_update=True)
                        if capsule is None:
                            continue
                        breaker = await session.scalar(select(TransferCircuitBreaker).where(
                            TransferCircuitBreaker.capsule_id == capsule_row_id,
                            TransferCircuitBreaker.target_agent_id == target_id,
                        ).with_for_update())
                        target_spec = next((agent for agent in node.agents if agent.id == target_id), None)
                        domains = list(dict.fromkeys([*(target_spec.role.lower().split() if target_spec else []), target_id]))
                        if breaker is None:
                            session.add(TransferCircuitBreaker(
                                id=uuid4(), tenant_id=tenant_id, workspace_id=workspace_id,
                                capsule_id=capsule_row_id, target_agent_id=target_id,
                                target_domain_tags=domains, tis_score=decision.impact.score,
                                application_count=decision.sample_count, active=True,
                            ))
                        else:
                            breaker.active = True
                            breaker.tis_score = decision.impact.score
                            breaker.application_count = decision.sample_count
                            breaker.target_domain_tags = domains
                        capsule.prohibited_contexts = list(dict.fromkeys([*capsule.prohibited_contexts, target_id, *domains]))
                        policy = await session.scalar(select(LearningPolicyRow).where(
                            LearningPolicyRow.source_agent_id == source_agent_id,
                            LearningPolicyRow.target_agent_id == target_id,
                        ).with_for_update())
                        if policy is not None:
                            policy.allowed = False
                        session.add(AuditLog(
                            id=uuid4(), tenant_id=tenant_id, workspace_id=workspace_id,
                            actor_id=None, action="learning_transfer.negative_transfer_quarantined",
                            target_type="knowledge_capsule", target_id=capsule_row_id,
                            details={"target_agent_id": target_id, "tis_score": decision.impact.score,
                                     "sample_count": decision.sample_count, "target_domain_tags": domains},
                        ))
                        negative_events.append({"capsule_id": str(capsule_id), "source_agent_id": source_agent_id,
                                                "target_agent_id": target_id, "tis_score": decision.impact.score,
                                                "sample_count": decision.sample_count})
                    learning_trials.pop((run_id, target_agent_id), None)
            if negative_events:
                emitter = RuntimeEventEmitter(self.redis, tenant_id, workspace_id, state.run_id)
                for payload in negative_events:
                    await emitter.emit(RuntimeEventType.NEGATIVE_TRANSFER_DETECTED, payload)

        async def consensus_handler(state: WorkflowState, node: Any) -> dict[str, Any]:
            config = node.consensus_config
            provider_names = {"openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm", "groq", "mistral", "together_ai"}

            async def ask(model_name: str, prompt: str, agent: str) -> str:
                provider, separator, model = model_name.partition("/")
                if not separator or provider not in provider_names:
                    raise ValueError("Consensus models must use an approved provider/model name")
                result = await self.gateway().complete(GatewayRequest(
                    tenant_id=tenant_id, workspace_id=workspace_id, provider=cast(Provider, provider),
                    model=model, messages=({"role": "user", "content": prompt},),
                    max_input_tokens=20_000, max_output_tokens=4_000, billing_mode="platform",
                    agent_name=f"consensus_{agent}", workflow_id=state.workflow_id, run_id=state.run_id,
                ))
                return result.content

            if isinstance(node, CrewNodeSpec):
                task_text = "\n".join(task.description for task in node.tasks)
                expected = self.output_schemas[node.tasks[-1].output_schema]
            else:
                task_text = str(node.coder_instructions or node.label)
                expected = None
            prompt = json.dumps({"task": task_text, "input": state.input_data, "completed_outputs": state.node_outputs}, ensure_ascii=False)
            drafts = await asyncio.gather(*(
                ask(model, f"Solve the task independently. Return only the requested structured output.\n{prompt}", f"draft_{index}")
                for index, model in enumerate(config.models)
            ))
            critics: list[str] = []
            for index, draft in enumerate(drafts):
                peer = drafts[(index + 1) % len(drafts)]
                critics.append(await ask(config.models[index], f"Cross-examine this peer answer for factual or logical errors. Be concise.\nPEER:\n{peer}\nYOUR DRAFT:\n{draft}", f"critic_{index}"))
            arbitration = await ask(config.arbiter_model,
                "Arbitrate the drafts and critiques. Return JSON with keys output (the final answer), confidence (0 to 1), and dissent_report.\n" +
                json.dumps({"drafts": drafts, "critiques": critics}, ensure_ascii=False), "arbiter")
            try:
                result = json.loads(arbitration)
                confidence = float(result["confidence"])
                final_output = result["output"]
                dissent = str(result.get("dissent_report", ""))
                if not 0 <= confidence <= 1:
                    raise ValueError("Arbiter confidence is outside [0,1]")
                if expected is not None:
                    if isinstance(final_output, str):
                        final_output = json.loads(final_output)
                    final_output = expected.model_validate(final_output).model_dump(mode="json")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError("Consensus arbiter must return schema-valid JSON and confidence") from error
            return {"output": final_output, "consensus_confidence": confidence, "dissent_report": dissent,
                    "drafts": drafts, "critiques": critics,
                    "approval_required": confidence < config.min_agreement_threshold}

        emitter = RuntimeEventEmitter(self.redis, tenant_id, workspace_id, run_id)
        spawner = self._dynamic_spawner(tenant_id, workspace_id, row.id, spec)
        crew_builder = await self._runtime_crew_builder(tenant_id, workspace_id, run_id, {DYNAMIC_TEAM_TOOL_ID: DynamicTeamMutatorTool(spawner)})
        registry = self.run_tool_registries[(tenant_id, workspace_id, run_id)]
        return FlowCompiler(
            self.checkpoints, emitter,
            self.sandbox_runner, crew_builder, rag_handler, usage_handler,
            model_resolver=self.tenant_model_client,
            capsule_handler=lambda capsule: save_capsule(self, capsule),
            learning_context_handler=learning_context_handler,
            learning_outcome_handler=learning_outcome_handler,
            consensus_handler=consensus_handler,
            required_tool_runner=registry.run,
            sandbox_file_reader=self.sandbox.read_run_file,
            dynamic_spawner=spawner,
        ).compile(spec, run_id, input_data)

    def _dynamic_spawner(self, tenant_id: UUID, workspace_id: UUID, workflow_id: UUID, spec: WorkflowSpec) -> DynamicSpawner:
        """Per-run service that lets directors reshape the team mid-run and optionally persist the change."""
        tools = {item.id for item in TOOLS} | {DYNAMIC_TEAM_TOOL_ID}
        models = tuple(dict.fromkeys(agent.model for node in spec.nodes if isinstance(node, CrewNodeSpec) for agent in node.agents))

        async def persist(record: SpawnRecord, evolved: WorkflowSpec) -> dict[str, Any]:
            from app import evolution

            return await evolution.record_mid_run_proposal(
                self, evolution.Scope(tenant_id, workspace_id), workflow_id, evolved,
                f"A director added {record.role} to {record.department_node_id} during a run: {record.rationale}".strip(),
                [{"op": "SPAWN_SPECIALIST_AGENT", "target_node_id": record.department_node_id, "summary": f"Added specialist {record.role}",
                  "request": {"op": "SPAWN_SPECIALIST_AGENT", "target_node_id": record.department_node_id, "role": record.role}}],
            )

        return DynamicSpawner(TeamTopologyMutator(tools, models), tools, models, persist_handler=persist)

    async def _after_run(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        from app import evolution

        try:
            await self.sandbox.retire_run(tenant_id, workspace_id, run_id)  # a run that ended must not keep a container
        except Exception:
            logging.getLogger("nexus.sandbox").exception("Run computer could not be removed", extra={"run_id": str(run_id)})

        try:
            await evolution.after_run(self, tenant_id, workspace_id, run_id)
        except Exception:
            logging.getLogger("nexus.evolution").exception("Generation fitness could not be updated", extra={"run_id": str(run_id)})

    def approvals(self, tenant_id: UUID, workspace_id: UUID, actor_id: UUID) -> ApprovalCoordinator:
        async def workflow_loader(run_id: UUID) -> CompiledWorkflow:
            return await self.compiled_workflow(tenant_id, workspace_id, run_id)

        async def routine_resumer(run_id: UUID) -> str:
            return await self.bot_runner(tenant_id, workspace_id, actor_id).resume_routine(run_id)

        return ApprovalCoordinator(
            self.engine, self.redis, self.checkpoints,
            tenant_id, workspace_id, actor_id, workflow_loader, routine_resumer,
            on_run_finished=lambda run_id: self._after_run(tenant_id, workspace_id, run_id),
        )


async def create_default_services(dispatcher: TaskDispatcher) -> AppServices:
    """Boot the plugin list (see `nexus_plugins/default.yaml`) and hand its services to the control plane."""
    kernel = await boot_default()
    root = kernel.root
    return AppServices(
        root.service(seams.DATABASE), root.service(seams.REDIS), root.service(seams.QDRANT), root.service(seams.SANDBOX), root.service(seams.SANDBOX_RUNNER), dispatcher,
        llm_service=root.service(seams.LLM), tools=root.service(seams.TOOLS), checkpoint_store=root.service(seams.CHECKPOINTS), kernel=kernel,
    )
