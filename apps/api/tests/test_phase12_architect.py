from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app.auth.context import TenantContext
from app.routers.architect import _approved_chat_models, _service
from architect.team_generator import (
    ArchitectWorkspaceContext,
    KnowledgeBaseDescriptor,
    MetaArchitectService,
    ToolDescriptor,
    VerifiedCapsuleDescriptor,
)
from crews.builder import CrewBuilder
from flows.compiler import FlowCompiler
from nexus_core_schema.models import (
    KnowledgeCapsuleSpec,
    PropagationScope,
    SensitivityLevel,
    WorkflowSpec,
)
from nexus_core_schema.template_outputs import BUILTIN_OUTPUT_SCHEMAS
from nexus_model_gateway.router import GatewayRequest, ModelRate, Provider


def _workspace() -> ArchitectWorkspaceContext:
    tenant_id, workspace_id = uuid4(), uuid4()
    capsule = KnowledgeCapsuleSpec(
        tenant_id=tenant_id, workspace_id=workspace_id, capsule_id=uuid4(),
        source_agent_id="sales_analyst_v1", source_role="Sales analyst",
        source_domain_tags=("sales", "csv", "forecasting"),
        trigger_preconditions="Use for monthly revenue CSV forecasting tasks.",
        distilled_heuristic="Parse dates explicitly, group revenue by month, and verify missing periods.",
        propagation_scope=PropagationScope.WORKSPACE_VERIFIED,
        sensitivity_level=SensitivityLevel.INTERNAL, confidence=0.97,
    )
    return ArchitectWorkspaceContext(
        tenant_id=tenant_id, workspace_id=workspace_id,
        available_models=("openai/gpt-4.1-mini", "anthropic/claude-sonnet-4"),
        mcp_tools=(ToolDescriptor(id="web_search", name="Web Search", description="Search public sources and verify citations.", server_id="research"),),
        knowledge_bases=(KnowledgeBaseDescriptor(id=uuid4(), name="Sales CSV Knowledge"),),
        verified_capsules=(VerifiedCapsuleDescriptor(capsule=capsule, impact_score=0.94),),
        output_schema_names=tuple(BUILTIN_OUTPUT_SCHEMAS),
    )


def _draft() -> dict[str, object]:
    return {
        "name": "Sales forecast with review",
        "summary": "Analyze sales records and prepare a reviewed monthly forecast.",
        "design_reasoning": ["Retrieve the workspace sales context.", "Use structured analysis then execute calculations safely.", "Pause before the report is shared."],
        "stages": [
            {
                "kind": "crew", "label": "Revenue Analyst", "purpose": "Analyze sales CSV and forecast next-month revenue.",
                "agents": [{"role": "Revenue analyst", "goal": "Forecast revenue from sales CSV data", "backstory": "A careful analyst who validates dates and totals.", "model": "openai/gpt-4.1-mini", "tool_ids": ["web_search"], "output_fields": {"forecast": "number", "assumptions": "string"}}],
                "tasks": [{"description": "Review the sales data and define forecast assumptions.", "expected_output": "A typed forecast plan", "output_fields": {"forecast": "number", "assumptions": "string"}}],
                "knowledge_base_ids": [],
            },
            {"kind": "sandbox", "label": "Run forecast", "purpose": "Use Python and pandas to calculate monthly revenue forecast.",
             "model": "openai/gpt-4.1-mini", "coder_instructions": "Run Python analysis on the supplied CSV.",
             "reviewer_instructions": "Check arithmetic and outputs."},
            {"kind": "approval", "label": "Manager approval", "purpose": "Approve the forecast report before external delivery."},
        ],
    }


def test_architect_selects_connected_chat_model_without_a_price_schedule() -> None:
    rates: dict[tuple[Provider, str], ModelRate] = {
        ("openai", "gpt-4.1-mini"): ModelRate(Decimal("0.40"), Decimal("1.60")),
    }
    discovered = {"openai/gpt-3.5-turbo", "openai/gpt-4.1-mini", "openai/text-embedding-3-small"}
    approved = _approved_chat_models(discovered)
    assert approved == ("openai/gpt-3.5-turbo", "openai/gpt-4.1-mini")  # unpriced models are allowed; embeddings are not
    assert _approved_chat_models({"ollama/llama3.2"}) == ("ollama/llama3.2",)
    context = _workspace().model_copy(update={"available_models": ("openai/gpt-4.1-mini",)})
    selected: list[str] = []

    class FakeGateway:
        async def complete(self, request: GatewayRequest) -> SimpleNamespace:
            selected.append(f"{request.provider}/{request.model}")
            return SimpleNamespace(content=json.dumps(_draft()))

    app = FastAPI()
    app.state.services = SimpleNamespace(model_rates=rates, gateway=lambda: FakeGateway())
    request = Request({"type": "http", "app": app})
    tenant = TenantContext(context.tenant_id, context.workspace_id, uuid4(), "owner")
    service = _service(request, tenant, context, None)
    asyncio.run(service.generate_workflow("Forecast monthly sales", context))
    assert selected == ["openai/gpt-4.1-mini"]
    try:
        _service(request, tenant, context, "openai/not-connected")
    except HTTPException as error:
        assert error.status_code == 422
        assert "not available in this workspace" in error.detail
    else:
        raise AssertionError("A model the workspace cannot reach must be rejected")


def test_meta_architect_generates_compilable_graph_and_binds_context() -> None:
    context = _workspace()
    calls = 0

    async def generate(prompt: str, output_model: type[BaseModel]) -> object:
        nonlocal calls
        calls += 1
        assert "Sales CSV Knowledge" in prompt
        return _draft()

    service = MetaArchitectService(generate, FlowCompiler.validate)
    spec, summary = asyncio.run(service.generate_workflow(
        "Analyze my sales CSV, forecast revenue, and wait for manager approval before sending the report.",
        context,
    ))
    assert calls == 1
    assert isinstance(WorkflowSpec.model_validate(spec.model_dump(mode="json")), WorkflowSpec)
    assert FlowCompiler.validate(spec) == spec
    analyst = next(agent for node in spec.nodes if node.kind == "crew" for agent in node.agents)
    assert analyst.tool_ids == ("web_search",)
    assert len(analyst.knowledge_capsule_ids) == 1
    assert summary["tools"] == ["web_search"]
    assert summary["knowledge_capsules"] == [str(analyst.knowledge_capsule_ids[0])]
    assert any(node.kind == "rag" for node in spec.nodes)
    assert any(node.kind == "approval" for node in spec.nodes)
    assert len(spec.layout) == len(spec.nodes)


def test_generated_task_schema_builds_as_pydantic_output() -> None:
    context = _workspace()

    async def generate(prompt: str, output_model: type[BaseModel]) -> object:
        return _draft()

    spec, _ = asyncio.run(MetaArchitectService(generate).generate_workflow(
        "Analyze sales data", context,
    ))
    crew = next(node for node in spec.nodes if node.kind == "crew")
    schema = CrewBuilder(BUILTIN_OUTPUT_SCHEMAS).schema_for_task(crew.tasks[0])
    assert schema.model_json_schema()["required"] == ["forecast", "assumptions"]


def test_workspace_skill_keywords_bind_to_generated_agents() -> None:
    context = _workspace().model_copy(update={
        "skill_slugs": ("monthly-revenue-check",),
        "skill_keywords": {"monthly-revenue-check": ("revenue", "forecast")},
    })

    async def generate(prompt: str, output_model: type[BaseModel]) -> object:
        return _draft()

    spec, _ = asyncio.run(MetaArchitectService(generate).generate_workflow("Forecast revenue", context))
    analyst = next(agent for node in spec.nodes if node.kind == "crew" for agent in node.agents)
    assert "monthly-revenue-check" in analyst.skill_ids


def test_refinement_preserves_workflow_identity_and_increments_version() -> None:
    context = _workspace()

    async def generate(prompt: str, output_model: type[BaseModel]) -> object:
        return _draft()

    service = MetaArchitectService(generate, FlowCompiler.validate)
    current, _ = asyncio.run(service.generate_workflow("Make a sales forecast", context, version=2))
    edited, _ = asyncio.run(service.generate_workflow(
        "Add an additional verification step", context, existing_workflow_spec=current,
    ))
    assert edited.id == current.id
    assert edited.version == current.version + 1
    assert FlowCompiler.validate(edited)
    assert edited.tenant_id == current.tenant_id and edited.workspace_id == current.workspace_id


def test_bot_generation_honors_available_preferred_model() -> None:
    context = _workspace()

    async def generate(prompt: str, output_model: type[BaseModel]) -> object:
        return {
            "name": "Sales Teammate", "description": "Reviews sales reports and highlights risks.",
            "model": "openai/gpt-4.1-mini", "routine_name": "Daily sales digest",
            "routine_markdown": "# Daily digest\n\nReview the latest sales results and list material changes.",
            "design_reasoning": ["Schedule a concise weekday review."],
        }

    service = MetaArchitectService(generate)
    bot, routine, _ = asyncio.run(service.generate_bot(
        "Review daily sales reports", context, preferred_model="anthropic/claude-sonnet-4",
    ))
    assert bot.model == "anthropic/claude-sonnet-4"
    assert routine.bot_id == bot.id
    assert routine.cron_expression == "0 9 * * 1-5"


def test_generated_inter_stage_learning_edge_is_quarantined_by_human_approval() -> None:
    context = _workspace()
    draft = _draft()
    second_crew = {
        "kind": "crew", "label": "Forecast Reviewer", "purpose": "Check forecast assumptions and totals.",
        "agents": [{"role": "Forecast reviewer", "goal": "Validate the forecast", "backstory": "An independent reviewer."}],
        "tasks": [{"description": "Validate forecast calculations and assumptions.", "expected_output": "A review result."}],
    }
    stages = cast(list[dict[str, object]], draft["stages"])
    draft["stages"] = [stages[0], stages[1], second_crew]

    async def generate(prompt: str, output_model: type[BaseModel]) -> object:
        return draft

    spec, _ = asyncio.run(MetaArchitectService(generate, FlowCompiler.validate).generate_workflow(
        "Analyze the sales forecast and have a second analyst verify it", context,
    ))
    edge = spec.learning_edges[0]
    assert edge.scope == PropagationScope.WORKFLOW_SCOPED
    assert edge.allow_heuristics and not edge.allow_code_patterns
    assert edge.require_human_approval


def test_architect_endpoints_are_registered() -> None:
    from app.main import create_app

    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    assert "/api/v1/architect/generate-workflow" in paths
    assert "/api/v1/architect/refine-workflow" in paths
    assert "/api/v1/architect/generate-bot" in paths


def test_generate_request_accepts_flat_input_files_only() -> None:
    from pydantic import ValidationError

    from app.routers.architect import GenerateWorkflowRequest

    ok = GenerateWorkflowRequest(user_requirement_prompt="Refactor auth", input_files={"auth.py": "print(1)", "workspace_manifest.json": "{}"})
    assert ok.input_files["auth.py"] == "print(1)" and ok.auto_run is True
    for bad in ({"src/auth.py": "x"}, {"..\\auth.py": "x"}, {".env": "SECRET=1"}, {"": "x"}):
        try:
            GenerateWorkflowRequest(user_requirement_prompt="x", input_files=bad)
        except ValidationError:
            continue
        raise AssertionError(f"{bad} must be rejected")
    try:
        GenerateWorkflowRequest(user_requirement_prompt="x", input_files={"big.txt": "a" * 1_000_001})
    except ValidationError:
        return
    raise AssertionError("Oversized input files must be rejected")


def test_one_unparseable_model_reply_does_not_fail_the_architect() -> None:
    from app.routers.architect import JSON_ATTEMPTS, _json_with_retry

    replies = iter(['{"name": "unfinished', '```json\n{"ok": true}\n```'])
    reminders: list[str] = []

    async def ask(reminder: str) -> str:
        reminders.append(reminder)
        return next(replies)

    assert asyncio.run(_json_with_retry(ask)) == {"ok": True}
    assert reminders[0] == "" and "valid JSON" in reminders[1], "the retry tells the model what went wrong"

    async def always_bad(_reminder: str) -> str:
        return "not json"

    try:
        asyncio.run(_json_with_retry(always_bad))
    except ValueError as error:
        assert "not valid JSON" in str(error) and JSON_ATTEMPTS == 3
    else:
        raise AssertionError("A model that never returns JSON must still surface an error")
