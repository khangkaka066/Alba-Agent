"""Phase 26: the teams a finished task is handed to, and the checks their sandbox teams run."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pytest

from flows.compiler import FlowCompiler
from nexus_core_schema.models import NexusGenSandboxNodeSpec, CrewNodeSpec, WorkflowSpec
from nexus_core_schema_templates.catalog import TEMPLATE_BY_ID
from nexus_core_schema_templates.studios import STUDIO_BY_ID, build_studio_graph, detect_studio

MARKETING = STUDIO_BY_ID["marketing-social-publishing-studio"]
ANALYTICS = STUDIO_BY_ID["analytics-optimization-studio"]
MODEL = "openai/gpt-4.1-mini"


def _spec(blueprint: Any, rigor: Literal["standard", "full_studio"]) -> WorkflowSpec:
    graph = build_studio_graph(blueprint, rigor, model=MODEL, director_model=MODEL)
    return WorkflowSpec(id=uuid4(), tenant_id=uuid4(), workspace_id=uuid4(), name="Next", version=1,
                        nodes=tuple(graph.nodes), edges=tuple(graph.edges), layout=graph.layout, modes=graph.modes)


@pytest.mark.parametrize(("blueprint", "agents", "channels"), [(MARKETING, 41, ("tiktok", "facebook", "youtube")), (ANALYTICS, 34, ())])
def test_each_next_team_compiles_with_the_advertised_size_and_declares_its_channels(blueprint: Any, agents: int, channels: tuple[str, ...]) -> None:
    graph = build_studio_graph(blueprint, "full_studio", model=MODEL, director_model=MODEL)
    spec = FlowCompiler.validate(_spec(blueprint, "full_studio"))
    assert graph.agent_count == agents and spec.modes.channels == channels
    assert TEMPLATE_BY_ID[blueprint.id].title == blueprint.title
    assert {node.id for node in spec.nodes if isinstance(node, NexusGenSandboxNodeSpec)} == {dept.key for dept in blueprint.wave_two}
    assert FlowCompiler.validate(_spec(blueprint, "standard")).modes.rigor == "standard"


def test_the_marketing_team_prepares_posts_and_never_claims_to_have_posted() -> None:
    spec = _spec(MARKETING, "full_studio")
    rules = {rule.pattern: rule.rule for rule in spec.modes.path_rules}
    assert "never state that anything was posted" in rules["release/**"]
    release = next(node for node in spec.nodes if node.id == "release")
    assert isinstance(release, CrewNodeSpec)
    checklist = next(task for task in release.tasks if task.id == "release_publishing_coordinator_task")
    assert "without posting anything" in checklist.description
    assert any("direct posting to the platforms is not wired yet" in note for note in MARKETING.readiness_notes)


def test_the_analytics_team_is_told_never_to_invent_numbers() -> None:
    spec = _spec(ANALYTICS, "full_studio")
    assert "never invent data" in {rule.pattern: rule.rule for rule in spec.modes.path_rules}["analytics/**"]
    sandbox = next(node for node in spec.nodes if node.id == "analysis_build")
    assert isinstance(sandbox, NexusGenSandboxNodeSpec) and "labelled an assumption" in sandbox.coder_instructions and "upstream/" in sandbox.coder_instructions
    assert ANALYTICS.channels == ()


def test_requests_pick_the_right_studio_and_an_explicit_choice_wins() -> None:
    expected = {
        "Tạo chiến dịch marketing để quảng bá video này": "marketing",
        "Build a marketing campaign and promote the film on social media": "marketing",
        "Create an analytics report of our KPIs and design A/B tests": "analytics",
        "Tạo báo cáo hiệu suất và tối ưu hóa A/B": "analytics",
    }
    for prompt, domain in expected.items():
        found = detect_studio(prompt)
        assert found is not None and found.domain == domain, prompt
    for prompt, domain in {"Create a documentary video campaign for the museum": "video", "Make a feature film about a lighthouse keeper": "film",
                           "Build a web app with a feature flag service": "software", "Make a 60s museum video for TikTok": "video",
                           "Build an analytics dashboard web app": "software"}.items():
        found = detect_studio(prompt)
        assert found is not None and found.domain == domain, prompt


def _passes(command: str, folder: Path) -> bool:
    return subprocess.run(["sh", "-c", command], cwd=folder, capture_output=True).returncode == 0


def test_the_sandbox_checks_accept_the_files_they_ask_for_and_reject_empty_ones(tmp_path: Path) -> None:
    if shutil.which("python") is None:
        pytest.skip("'python' executable is not on PATH to run sandbox verification checks")
    good: dict[str, dict[str, str]] = {
        "calendar_build": {"marketing/content_calendar.csv": "date,channel,format,title,caption,asset\n2026-11-10,tiktok,video,Teaser,Hi,teaser.mp4\n",
                           "marketing/channel_packages.json": '{"tiktok":{"caption":"a"},"youtube":{"caption":"b"},"facebook":{"caption":"c"}}'},
        "kpi_tracker": {"marketing/kpi_tracker.csv": "metric,channel,target,unit,week_1,week_2,week_3,week_4\nviews,tiktok,10000,count,,,,\n",
                        "marketing/report_template.html": "<html><body><table></table></body></html>"},
        "analysis_build": {"analytics/kpi_baseline.csv": "kpi,value,unit,source_file\nviews,n/a,count,assumption\n", "analytics/report.html": "<html><svg></svg></html>"},
        "experiment_pack": {"analytics/experiment_plan.json": '[{"id":"e1","hypothesis":"h"}]', "analytics/forecast.csv": "period,low,expected,high,assumption\nQ1,1,2,3,assumption\n"},
    }
    checks = {dept.key: dept.verification for blueprint in (MARKETING, ANALYTICS) for dept in blueprint.wave_two}
    for key, files in good.items():
        folder = tmp_path / key
        for name, content in files.items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(content)
        assert _passes(checks[key], folder), f"{key} should accept valid files"
        for name in files:
            (folder / name).write_text("")
        assert not _passes(checks[key], folder), f"{key} should reject empty files"
