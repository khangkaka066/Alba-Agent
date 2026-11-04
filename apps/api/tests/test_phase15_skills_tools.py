from __future__ import annotations

import asyncio
import csv
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from agent_skills import SkillLoader, SkillSpec
from nexus_builtin_tools import BuiltinToolRegistry, TOOLS, ToolContext
from nexusgen_bridge.sandbox_team import NexusGenSandboxRunner
from autogen_core.models import ChatCompletionClient
from nexus_core_schema.models import NexusGenSandboxNodeSpec


ROOT = Path(__file__).resolve().parents[3]


SAMPLE_SKILL = """---
name: Revenue Review
slug: revenue-review
category: finance
description: "Review revenue figures against stated definitions."
trigger_keywords: ["revenue", "forecast"]
required_tools: []
recommended_models: []
---

## Purpose
Check revenue figures.

## Standard operating procedure
Define each metric before using it.

## Guardrails
Never invent a figure.
"""


def test_no_skill_ships_with_the_product_and_workspace_skills_load_from_their_own_directory(tmp_path: Path) -> None:
    """Only skills whose quality was checked belong in the product; the packaged catalog is empty until then."""
    assert SkillLoader().catalog() == ()
    (tmp_path / "revenue-review.md").write_text(SAMPLE_SKILL)
    loader = SkillLoader([tmp_path])
    catalog = loader.catalog()
    assert [item["slug"] for item in catalog] == ["revenue-review"]
    assert all("body" not in item for item in catalog)
    full = loader.get("revenue-review")
    assert "Standard operating procedure" in full.body
    assert SkillSpec.from_markdown(full.to_markdown()).slug == full.slug


def test_only_assigned_or_task_matched_skill_enters_agent_prompt(tmp_path: Path) -> None:
    (tmp_path / "revenue-review.md").write_text(SAMPLE_SKILL)
    loader = SkillLoader([tmp_path])
    assert "Define each metric" not in str(loader.catalog())
    assigned = loader.inject("You are an analyst.", assigned=("revenue-review",))
    assert "Guardrails" in assigned
    task_matched = loader.inject("Analyze this revenue CSV", task="forecast monthly revenue")
    assert "Revenue Review" in task_matched


def test_verified_high_tis_capsule_promotes_to_workspace_skill(tmp_path: Path) -> None:
    (tmp_path / "revenue-review.md").write_text(SAMPLE_SKILL)
    loader = SkillLoader((tmp_path,))

    @dataclass
    class Capsule:
        propagation_scope: str = "WORKSPACE_VERIFIED"
        distilled_heuristic: str = "Decode CSV using utf-8-sig, then fall back to cp1252 only after a decode error."

    promoted = loader.promote_capsule("revenue-review", Capsule(), tis=0.42)
    assert "Learned Best Practices & Edge Cases" in promoted.body
    assert "utf-8-sig" in promoted.body
    assert (tmp_path / "revenue-review.md").exists()
    with pytest.raises(PermissionError):
        loader.promote_capsule("revenue-review", Capsule(propagation_scope="CREW_LOCAL"), tis=0.8)
    with pytest.raises(ValueError):
        loader.promote_capsule("revenue-review", Capsule(), tis=0.01)


def test_builtin_tools_local_document_sql_report_chart_and_security(tmp_path: Path) -> None:
    async def run() -> None:
        context = ToolContext(str(uuid4()), str(uuid4()), str(uuid4()), tmp_path)
        registry = BuiltinToolRegistry(context)
        assert len(registry.descriptors()) == 12
        assert {tool.id for tool in registry.descriptors()} == {tool.id for tool in TOOLS}
        assert len(registry.nexusai_tools()) == 12
        assert len(registry.nexusgen_tools()) == 12

        sample = tmp_path / "sample.csv"
        sample.write_text("month,revenue\nJan,12\nFeb,19\n", encoding="utf-8")
        parsed = await registry.run("document_parser", {"path": "sample.csv"})
        assert parsed["columns"] == ["month", "revenue"]
        assert parsed["rows"][1] == ["Feb", "19"]

        database = tmp_path / "read-only.db"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE sales(month TEXT, revenue INTEGER)")
        connection.execute("INSERT INTO sales VALUES ('Jan', 12)")
        connection.commit()
        connection.close()
        context.database_urls["sales"] = f"sqlite:{database}"
        result = await registry.run("safe_sql", {"database": "sales", "query": "SELECT month, revenue FROM sales", "limit": 10})
        assert result["rows"] == [("Jan", 12)]
        with pytest.raises(PermissionError):
            await registry.run("safe_sql", {"database": "sales", "query": "DELETE FROM sales"})

        report = await registry.run("report_exporter", {"format": "markdown", "filename": "brief", "content": "# Result"})
        assert (tmp_path / report["artifact"]).read_text(encoding="utf-8") == "# Result"
        xlsx = await registry.run("report_exporter", {"format": "xlsx", "filename": "table", "rows": [["month", "revenue"], ["Jan", 12]]})
        assert zipfile_is_valid(tmp_path / xlsx["artifact"])
        chart = await registry.run("chart_generator", {"kind": "bar", "labels": ["Jan", "Feb"], "values": [12, 19]})
        assert (tmp_path / chart["artifact"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        with pytest.raises(PermissionError):
            await registry.run("web_scraper", {"url": "http://127.0.0.1/secret"})
        disabled_registry = BuiltinToolRegistry(ToolContext(str(uuid4()), str(uuid4()), str(uuid4()), tmp_path, frozenset()))
        with pytest.raises(PermissionError):
            await disabled_registry.run("document_parser", {"path": "sample.csv"})
    asyncio.run(run())


def test_custom_skill_is_injected_once_into_sandbox_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    import nexusgen_bridge.sandbox_team as bridge

    messages: list[str] = []

    class ModelClient:
        async def close(self) -> None:
            return None

    class Agent:
        def __init__(self, **kwargs: object) -> None:
            if kwargs.get("name") == "coder":
                messages.append(str(kwargs["system_message"]))

    class Team:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def run_stream(self, *, task: str) -> AsyncIterator[SimpleNamespace]:
            yield SimpleNamespace(source="reviewer", content="Please verify the result", models_usage=None)

    monkeypatch.setattr(bridge, "AssistantAgent", Agent)
    monkeypatch.setattr(bridge, "RoundRobinGroupChat", Team)
    runner = NexusGenSandboxRunner(SimpleNamespace(), lambda model: cast(ChatCompletionClient, ModelClient()))  # type: ignore[arg-type]

    async def resolve_skills(tenant_id: object, workspace_id: object, slugs: tuple[str, ...]) -> dict[str, str]:
        assert "workspace-analysis" in slugs
        return {"workspace-analysis": "Only use approved workspace revenue definitions."}

    runner.set_skill_resolver(resolve_skills)
    spec = NexusGenSandboxNodeSpec(
        id="sandbox", label="Python analysis", coder_model="openai/gpt-4.1-mini",
        reviewer_model="openai/gpt-4.1-mini", verification_command="python -m compileall .",
        skill_ids=("workspace-analysis",),
    )
    emitter = SimpleNamespace(tenant_id=uuid4(), workspace_id=uuid4(), run_id=uuid4())

    async def emit(*args: object) -> None:
        return None

    emitter.emit = emit
    asyncio.run(runner.run("analyze monthly revenue", spec, emitter))  # type: ignore[arg-type]
    assert len(messages) == 1
    assert messages[0].count("Only use approved workspace revenue definitions.") == 1


def zipfile_is_valid(path: Path) -> bool:
    import zipfile
    with zipfile.ZipFile(path) as archive:
        return "xl/worksheets/sheet1.xml" in archive.namelist()


def test_builtin_tools_route_through_scoped_service_hooks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import nexus_builtin_tools.registry as tools_module

    calls: list[str] = []

    def fake_http(url: str, **kwargs: object) -> bytes:
        calls.append(url)
        return b'<html><body><article><p>Verified source</p><a href="https://example.com/source">Source</a></article></body></html>'

    async def shell(command: str, timeout: int) -> dict[str, object]:
        calls.append("shell")
        return {"stdout": command, "exit_code": 0}

    async def browser(action: str, arguments: dict[str, str]) -> bytes:
        calls.append("browser")
        return b"PNG frame"

    async def media(kind: str, payload: dict[str, object]) -> dict[str, str]:
        calls.append("media")
        return {"kind": kind}

    async def rag(query: str) -> list[dict[str, str]]:
        calls.append("rag")
        return [{"text": query, "citation": "doc-1"}]

    async def delegate(workflow_id: str, inputs: dict[str, object]) -> dict[str, object]:
        calls.append("delegate")
        return {"workflow_id": workflow_id, "inputs": inputs}

    async def guard(kind: str, description: str) -> None:
        calls.append("approved")

    monkeypatch.setattr(tools_module, "_http", fake_http)
    registry = BuiltinToolRegistry(ToolContext(
        str(uuid4()), str(uuid4()), str(uuid4()), tmp_path,
        shell=shell, browser=browser, media=media, rag_query=rag,
        workflow_delegate=delegate, boundary_guard=guard,
    ))

    async def run() -> None:
        assert "Verified source" in (await registry.run("web_search", {"query": "revenue"}))["markdown"]
        assert (await registry.run("web_scraper", {"url": "https://example.com/source"}))["links"][0]["text"] == "Source"
        assert (await registry.run("sandbox_shell", {"command": "pwd"}))["exit_code"] == 0
        assert await registry.run("browser_automation", {"action": "screenshot"}) == b"PNG frame"
        assert (await registry.run("media_generation", {"kind": "image"}))["kind"] == "image"
        assert (await registry.run("knowledge_rag", {"query": "budget"}))[0]["citation"] == "doc-1"
        assert (await registry.run("peer_workflow", {"workflow_id": "peer", "inputs": {"x": 1}}))["inputs"] == {"x": 1}
        assert "Verified source" in (await registry.run("http_webhook", {"url": "https://example.com/webhook", "method": "POST"}))["body"]

    asyncio.run(run())
    assert calls.count("approved") == 1
    assert {"shell", "browser", "media", "rag", "delegate"} <= set(calls)


def test_every_seed_skill_requires_only_tools_that_exist() -> None:
    """A skill naming a tool the registry lacks makes any run that binds it fail at crew build time."""
    known = {tool.id for tool in TOOLS}
    for slug, skill in SkillLoader()._skills.items():
        assert isinstance(skill, SkillSpec)
        missing = set(skill.required_tools) - known
        assert not missing, f"{slug} requires unknown tools {sorted(missing)}"
