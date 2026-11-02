from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from nexus_core_schema import WorkflowSpec
from app.auth.context import TenantContext, decode_voice_token, issue_voice_token


def test_workflow_round_trip_and_exported_schema() -> None:
    tenant_id, workspace_id, workflow_id = uuid4(), uuid4(), uuid4()
    spec = WorkflowSpec.model_validate({
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
        "id": str(workflow_id),
        "name": "Review a change",
        "version": 1,
        "nodes": [
            {"id": "start", "kind": "start"},
            {
                "id": "crew", "kind": "crew", "label": "Review",
                "agents": [{"id": "reviewer", "role": "Reviewer", "goal": "Check the change", "model": "approved-model"}],
                "tasks": [{"id": "review", "agent_id": "reviewer", "description": "Inspect code", "expected_output": "Findings", "output_schema": "ReviewResult"}],
            },
        ],
        "edges": [{"source": "start", "target": "crew"}],
    })
    assert WorkflowSpec.model_validate_json(spec.model_dump_json()) == spec
    schema_path = Path(__file__).resolve().parents[3] / "packages/core-schema/typescript/schemas/WorkflowSpec.schema.json"
    exported = json.loads(schema_path.read_text())
    assert exported == WorkflowSpec.model_json_schema()


def test_workflow_rejects_cross_reference_and_unknown_fields() -> None:
    base = {
        "tenant_id": str(uuid4()), "workspace_id": str(uuid4()), "id": str(uuid4()),
        "name": "Invalid", "version": 1,
        "nodes": [{"id": "start", "kind": "start"}],
        "edges": [{"source": "start", "target": "missing"}],
    }
    with pytest.raises(ValidationError, match="unknown node"):
        WorkflowSpec.model_validate(base)
    base["edges"] = []
    base["unrecognized"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        WorkflowSpec.model_validate(base)


def test_voice_token_is_limited_to_the_issued_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_SECRET_KEY", "test-voice-token-secret-with-32-bytes")
    tenant_id, workspace_id, user_id, bot_id = (uuid4() for _ in range(4))
    context = TenantContext(tenant_id, workspace_id, user_id, "builder")
    token = issue_voice_token(context, bot_id)
    assert decode_voice_token(token, bot_id) == (tenant_id, workspace_id, user_id)
    with pytest.raises(ValueError, match="Invalid voice token"):
        decode_voice_token(token, uuid4())
