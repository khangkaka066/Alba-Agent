"""Validation for the bundled tenant-neutral workflow templates."""

from __future__ import annotations

from uuid import UUID

from nexus_core_schema_templates.catalog import TEMPLATES
from nexus_core_schema.models import WorkflowSpec
from nexus_core_schema.template_outputs import BUILTIN_OUTPUT_SCHEMAS


def test_catalog_templates_are_complete_valid_graphs_and_have_declared_outputs() -> None:
    assert len(TEMPLATES) == 10
    output_names = set(BUILTIN_OUTPUT_SCHEMAS)
    for template in TEMPLATES:
        document = template.workflow_document()
        spec = WorkflowSpec.model_validate({
            "id": UUID("00000000-0000-4000-8000-000000000001"),
            "tenant_id": UUID("00000000-0000-4000-8000-000000000001"),
            "workspace_id": UUID("00000000-0000-4000-8000-000000000001"),
            **document,
        })
        assert len(spec.nodes) >= 4
        assert len(spec.edges) >= 3
        assert all(task.output_schema in output_names or task.output_schema_json for node in spec.nodes if node.kind == "crew" for task in node.tasks)
        assert set(template.layout) == {node.id for node in spec.nodes}
        if template.bot is not None:
            assert template.bot.routines


def test_market_and_operations_templates_create_scoped_knowledge_and_bot_seeds() -> None:
    for template in TEMPLATES:
        if template.knowledge_base_name:
            rag_nodes = [node for node in template.nodes if node.kind == "rag"]
            assert rag_nodes
            assert all(node.knowledge_base_id.int == 0 for node in rag_nodes)
        if template.bot is not None:
            assert template.bot.routines and all(len(routine.cron_expression.split()) == 5 for routine in template.bot.routines)

