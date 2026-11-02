"""Asynchronous shadow evaluation for verified tenant golden traces."""

from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.models import AuditLog, DistillationRecommendation, GoldenTraceRecord, TokenUsageLog, Workflow, WorkflowRun
from app.models.scope import scoped_session
from nexus_core_schema.models import WorkflowSpec
from nexus_model_gateway.router import GatewayRequest


async def shadow_distill(services: Any, tenant_id: UUID, workspace_id: UUID,
                         agent_id: str, task_signature: str) -> None:
    """Evaluate approved cheaper models; persist only passing recommendations."""
    lock_key = f"nexus:{tenant_id}:{workspace_id}:distill:{agent_id}:{task_signature}"
    if not await services.redis.set(lock_key, "running", ex=3600, nx=True):
        return
    try:
        async with scoped_session(services.engine, tenant_id, workspace_id) as session:
            traces = (await session.scalars(select(GoldenTraceRecord).where(
                GoldenTraceRecord.agent_id == agent_id,
                GoldenTraceRecord.task_signature == task_signature,
            ).order_by(GoldenTraceRecord.created_at).limit(100))).all()
            if len(traces) < 20:
                return
            workflows = (await session.scalars(select(Workflow).order_by(Workflow.version.desc()))).all()
            matching: tuple[str, str] | None = None
            for workflow in workflows:
                spec = WorkflowSpec.model_validate(workflow.spec)
                for node in spec.nodes:
                    if node.kind != "crew" or not any(agent.id == agent_id for agent in node.agents):
                        continue
                    task = next((task for task in node.tasks if task.agent_id == agent_id), None)
                    if task is not None:
                        matching = (task.description, task.output_schema)
                        break
                if matching:
                    break
            if matching is None:
                return
            existing = await session.scalar(select(DistillationRecommendation.id).where(
                DistillationRecommendation.agent_id == agent_id,
                DistillationRecommendation.task_signature == task_signature,
            ).limit(1))
            if existing is not None:
                return
            # Copy values while the scoped session is open.
            trace_data = cast(list[dict[str, Any]], [{"input": row.input_payload, "expected": row.verified_output,
                           "cost": float(row.cost_usd), "latency_ms": row.latency_ms,
                           "run_id": str(row.run_id)} for row in traces])
            task_description, schema_name = matching

        candidates = tuple(item.strip() for item in os.environ.get(
            "NEXUS_DISTILLATION_CANDIDATES", "openai/gpt-4o-mini,gemini/gemini-2.5-flash,deepseek/deepseek-chat"
        ).split(",") if item.strip())
        baseline_cost = sum(item["cost"] for item in trace_data) / len(trace_data)
        if baseline_cost <= 0:
            return
        results: list[tuple[str, dict[str, float], list[dict[str, object]]]] = []
        examples = [{"input": item["input"], "output": item["expected"]} for item in trace_data[-3:]]
        schema = services.output_schemas.get(schema_name)
        for full_model in candidates:
            provider, separator, model = full_model.partition("/")
            if not separator:
                continue
            valid = 0
            similarities: list[float] = []
            candidate_costs: list[float] = []
            candidate_latency: list[int] = []
            for item in trace_data[: min(10, len(trace_data))]:
                prompt = json.dumps({"task": task_description, "few_shot_examples": examples,
                                     "input": item["input"]}, ensure_ascii=False)
                response = await services.gateway().complete(GatewayRequest(
                    tenant_id=tenant_id, workspace_id=workspace_id, provider=cast(Any, provider),
                    model=model, messages=({"role": "user", "content": prompt},),
                    max_input_tokens=20_000, max_output_tokens=4_000,
                    billing_mode="platform", agent_name=f"shadow_{agent_id}",
                ))
                candidate_costs.append(float(response.usage.total_cost_usd))
                candidate_latency.append(response.usage.latency_ms)
                try:
                    parsed: Any = json.loads(response.content)
                    if schema is not None:
                        parsed = schema.model_validate(parsed).model_dump(mode="json")
                    valid += 1
                    actual = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
                    expected = json.dumps(item["expected"], sort_keys=True, ensure_ascii=False)
                    similarities.append(SequenceMatcher(None, actual, expected).ratio())
                except (ValueError, TypeError):
                    similarities.append(0.0)
            schema_rate = valid / min(10, len(trace_data))
            similarity = sum(similarities) / len(similarities)
            avg_candidate_cost = sum(candidate_costs) / max(1, len(candidate_costs))
            avg_baseline = sum(item["cost"] for item in trace_data[:len(candidate_costs)]) / max(1, len(candidate_costs))
            cost_reduction = 1 - avg_candidate_cost / max(avg_baseline, 1e-12)
            baseline_latency = sum(item["latency_ms"] for item in trace_data[:len(candidate_latency)]) / max(1, len(candidate_latency))
            speedup = baseline_latency / max(1, sum(candidate_latency) / max(1, len(candidate_latency)))
            metrics = {"schema_validity_rate": schema_rate, "semantic_similarity": similarity,
                       "latency_speedup": speedup, "cost_reduction": cost_reduction}
            if schema_rate >= 0.95 and similarity >= 0.95 and cost_reduction >= 0.40:
                results.append((full_model, metrics, examples))

        if results:
            async with scoped_session(services.engine, tenant_id, workspace_id) as session:
                for model, metrics, shots in results:
                    session.add(DistillationRecommendation(
                        tenant_id=tenant_id, workspace_id=workspace_id,
                        agent_id=agent_id, task_signature=task_signature,
                        candidate_model=model, metrics=metrics, few_shot_examples=shots,
                        status="recommended",
                    ))
    finally:
        await services.redis.delete(lock_key)


async def monitor_live_distillation(services: Any, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
    """Watch model-bearing run outcomes and restore a prior workflow after drift."""
    async with scoped_session(services.engine, tenant_id, workspace_id) as session:
        models = set((await session.scalars(select(TokenUsageLog.model).where(TokenUsageLog.run_id == run_id))).all())
        if not models:
            return
        recommendations = (await session.scalars(select(DistillationRecommendation).where(
            DistillationRecommendation.status == "applied",
            DistillationRecommendation.candidate_model.in_(models),
        ).with_for_update())).all()
        for recommendation in recommendations:
            observed = (await session.execute(select(WorkflowRun.status).join(
                TokenUsageLog, TokenUsageLog.run_id == WorkflowRun.id,
            ).where(
                TokenUsageLog.model == recommendation.candidate_model,
                TokenUsageLog.agent_name == recommendation.agent_id,
            ).order_by(WorkflowRun.created_at.desc()).limit(20))).scalars().all()
            if len(observed) < 5:
                continue
            error_rate = sum(status == "failed" for status in observed) / len(observed)
            raw_validity = recommendation.metrics.get("schema_validity_rate", 1.0)
            schema_validity = float(raw_validity) if isinstance(raw_validity, (int, float)) else 1.0
            baseline = max(0.05, 1 - schema_validity)
            if error_rate <= baseline * 1.2:
                continue
            rollback = recommendation.metrics.get("rollback")
            if not isinstance(rollback, dict):
                continue
            workflows = (await session.scalars(select(Workflow).order_by(Workflow.version.desc()))).all()
            source = next((workflow for workflow in workflows if any(
                node.kind == "crew" and any(agent.id == recommendation.agent_id for agent in node.agents)
                for node in WorkflowSpec.model_validate(workflow.spec).nodes
            )), None)
            prior_agents = rollback.get("agents", {})
            prior_tasks = rollback.get("tasks", {})
            if source is None or not isinstance(prior_agents, dict) or not isinstance(prior_tasks, dict):
                continue
            spec = WorkflowSpec.model_validate(source.spec)
            nodes: list[Any] = []
            for node in spec.nodes:
                if node.kind != "crew":
                    nodes.append(node)
                    continue
                agents = tuple(agent.model_copy(update={"model": prior_agents[recommendation.agent_id]})
                               if agent.id == recommendation.agent_id and isinstance(prior_agents.get(recommendation.agent_id), str) else agent
                               for agent in node.agents)
                tasks = tuple(task.model_copy(update={"description": prior_tasks[task.id]})
                              if isinstance(prior_tasks.get(task.id), str) else task for task in node.tasks)
                nodes.append(node.model_copy(update={"agents": agents, "tasks": tasks}))
            latest = await session.scalar(select(func.max(Workflow.version)).where(Workflow.name == source.name))
            version = int(latest or source.version) + 1
            restored = spec.model_copy(update={"id": uuid4(), "version": version, "nodes": tuple(nodes)})
            session.add(Workflow(id=restored.id, tenant_id=tenant_id, workspace_id=workspace_id,
                                 name=source.name, version=version, spec=restored.model_dump(mode="json")))
            recommendation.status = "rolled_back"
            session.add(AuditLog(tenant_id=tenant_id, workspace_id=workspace_id, actor_id=None,
                                 action="finops.distillation_auto_rollback", target_type="distillation_recommendation",
                                 target_id=recommendation.id,
                                 details={"observed_error_rate": error_rate, "baseline_error_rate": baseline,
                                          "rollback_workflow_version": version}))
