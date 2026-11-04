"""Generation lifecycle against PostgreSQL with row-level security: proposal, promotion, fitness, autonomous rollback."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import evolution
from app.models import Workflow, WorkflowEvolutionPolicy, WorkflowTopologyVersion
from app.models.scope import scoped_session
from nexus_core_schema.models import NexusGenSandboxNodeSpec, CrewNodeSpec, WorkflowSpec
from nexus_core_schema_templates.studios import STUDIO_BY_ID, build_studio_graph
from sqlalchemy import select


def _spec(tenant: UUID, workspace: UUID) -> WorkflowSpec:
    graph = build_studio_graph(STUDIO_BY_ID["cinematic-video-documentary-studio"], "standard", model="openai/gpt-4.1-mini", director_model="openai/gpt-4.1-mini")
    return WorkflowSpec(id=uuid4(), tenant_id=tenant, workspace_id=workspace, name=f"Evolving film studio {uuid4().hex[:6]}", version=1,
                        nodes=tuple(graph.nodes), edges=tuple(graph.edges), layout=graph.layout, modes=graph.modes)


def _state(spec: WorkflowSpec, *, complete: float, gate_passed: bool, reasons: tuple[str, ...] = ()) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    declared = [(node.id, path) for node in spec.nodes if isinstance(node, (CrewNodeSpec, NexusGenSandboxNodeSpec)) for path in node.declared_artifact_paths()]
    keep = declared[: int(len(declared) * complete)]
    for node_id, path in declared:
        contract = outputs.setdefault(node_id, {"artifact_contract": {"passed": True, "verified": [], "recovered": [], "missing": [], "invalid": []}})["artifact_contract"]
        contract["verified" if (node_id, path) in keep else "missing"].append(path)
        contract["passed"] = not contract["missing"]
    outputs["quality_gate__gate"] = {"gate_passed": gate_passed, "failing_department": "story" if reasons else "", "reasons": list(reasons), "missing": []}
    outputs["quality_gate__loops"] = 0
    return {"node_outputs": outputs, "completed_nodes": ["start"]}


def test_generation_lifecycle_with_governance_and_autonomous_rollback() -> None:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL with the runtime role is required")

    async def check() -> None:
        tenant, workspace = uuid4(), uuid4()
        admin = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"])
        app_engine = create_async_engine(os.environ["NEXUS_TEST_APP_DATABASE_URL"])
        services = cast(Any, SimpleNamespace(engine=app_engine, model_rates={}))
        scope = evolution.Scope(tenant, workspace)
        spec = _spec(tenant, workspace)
        started = datetime.now(timezone.utc) - timedelta(minutes=10)

        async def add_run(workflow_id: UUID, state: dict[str, Any], status: str, seconds: float, cost: float) -> UUID:
            run_id = uuid4()
            async with admin.begin() as connection:
                await connection.execute(text(
                    "INSERT INTO workflow_runs (id, tenant_id, workspace_id, workflow_id, input_data, status, started_at, finished_at) "
                    "VALUES (:id, :t, :w, :wf, '{}'::jsonb, :status, :s, :f)"),
                    {"id": run_id, "t": tenant, "w": workspace, "wf": workflow_id, "status": status, "s": started, "f": started + timedelta(seconds=seconds)})
                await connection.execute(text(
                    "INSERT INTO run_checkpoints (id, tenant_id, workspace_id, run_id, sequence, state) VALUES (:id, :t, :w, :r, 1, CAST(:state AS jsonb))"),
                    {"id": uuid4(), "t": tenant, "w": workspace, "r": run_id, "state": __import__("json").dumps(state)})
                await connection.execute(text(
                    "INSERT INTO token_usage_logs (id, tenant_id, workspace_id, workflow_id, run_id, agent_name, provider, model, prompt_tokens, completion_tokens, "
                    "total_cost_usd, sandbox_compute_seconds, latency_ms, managed_charge) VALUES (:id, :t, :w, :wf, :r, 'a', 'openai', 'gpt-4.1-mini', 10, 10, :cost, 0, 100, true)"),
                    {"id": uuid4(), "t": tenant, "w": workspace, "wf": workflow_id, "r": run_id, "cost": cost})
            return run_id

        try:
            async with admin.begin() as connection:
                await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Evolution')"), {"id": tenant})
                await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'Evolution')"), {"id": workspace, "t": tenant})
                await connection.execute(text("INSERT INTO workflows (id, tenant_id, workspace_id, name, version, spec) VALUES (:id, :t, :w, :n, 1, CAST(:spec AS jsonb))"),
                                         {"id": spec.id, "t": tenant, "w": workspace, "n": spec.name, "spec": spec.model_dump_json()})
            # v1: a finished run whose quality review flags work no agent owns
            await add_run(spec.id, _state(spec, complete=0.9, gate_passed=False, reasons=("The narration needs audio ducking under the music",)), "completed", 100, 1.0)

            proposed = await evolution.evolve(services, scope, spec.id)
            assert proposed["status"] == "proposed" and proposed["version"] == 2
            assert any("Audio & Subtitle Sync Specialist" in lines for lines in proposed["diff_lines"])
            assert proposed["applied"][0]["op"] == "SPAWN_SPECIALIST_AGENT" and proposed["applied"][0]["request"]["role"]
            again = await evolution.evolve(services, scope, spec.id)
            assert again["status"] == "pending_proposal"

            async with scoped_session(app_engine, tenant, workspace) as session:
                assert await session.get(Workflow, UUID(proposed["workflow_id"])) is None  # a proposal is not a workflow yet
                policy, versions = await evolution.ensure_lineage(session, scope, spec.id)
                row = next(item for item in versions if item.version_number == 2)
                assert row.status == "proposed" and policy.active_workflow_id == spec.id and row.parent_version == 1
                await evolution.promote(session, scope, policy, versions, row, "approved in test")
            async with scoped_session(app_engine, tenant, workspace) as session:
                promoted = await session.get(Workflow, UUID(proposed["workflow_id"]))
                assert promoted is not None and promoted.version == 2
                stored = await session.scalar(select(WorkflowEvolutionPolicy))
                assert stored is not None and stored.active_workflow_id == promoted.id and stored.active_version == 2

            # v2 performs terribly: the autonomous governor must restore v1
            async with scoped_session(app_engine, tenant, workspace) as session:
                policy = cast(WorkflowEvolutionPolicy, await session.scalar(select(WorkflowEvolutionPolicy)))
                policy.auto_evolve_policy = "FULLY_AUTONOMOUS"
            failed_run = await add_run(promoted.id, {"node_outputs": {}, "completed_nodes": ["start"]}, "failed", 600, 9.0)
            outcome = await evolution.after_run(services, tenant, workspace, failed_run)
            assert outcome is not None and outcome["status"] == "rolled_back" and outcome["to_version"] == 1
            assert outcome["child_fitness"] < outcome["parent_fitness"] - 0.05

            async with scoped_session(app_engine, tenant, workspace) as session:
                policy, versions = await evolution.ensure_lineage(session, scope, spec.id)
                await evolution.refresh_metrics(session, versions)
                view = evolution.lineage_view(policy, versions)
            by_version = {item["version"]: item for item in view["generations"]}
            assert view["active_version"] == 1 and by_version[2]["status"] == "rolled_back" and by_version[1]["status"] == "active"
            assert by_version[1]["fitness"] is not None and by_version[2]["fitness"] is not None and by_version[2]["fitness"] < by_version[1]["fitness"]
            assert [point["version"] for point in view["trend"]] == [1, 2] and view["lineage"] == "v1 → v2"

            # the autonomous governor must not re-propose a change it has already rolled back
            repeat = await evolution.evolve(services, scope, spec.id, origin="autonomous", auto=True)
            assert repeat["status"] == "no_change" and "already rolled back" in repeat["message"]

            # tenant isolation: another workspace sees none of this lineage
            async with scoped_session(app_engine, uuid4(), uuid4()) as session:
                assert (await session.scalars(select(WorkflowTopologyVersion))).all() == []
        finally:
            # audit logs are immutable by design, so the throw-away tenant stays; its random IDs cannot collide
            await admin.dispose()
            await app_engine.dispose()

    asyncio.run(check())
