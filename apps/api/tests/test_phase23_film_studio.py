"""Feature film studio blueprint and the social channels that only teams which publish declare."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.routers import templates as template_router  # noqa: F401  (the gallery must keep importing with the new blueprint)
from nexus_core_schema.models import AutoGenSandboxNodeSpec, CrewNodeSpec, WorkflowModesSpec, WorkflowSpec
from nexus_core_schema_templates.catalog import TEMPLATE_BY_ID
from nexus_core_schema_templates.studios import STUDIO_BLUEPRINTS, STUDIO_BY_ID, build_studio_graph, detect_studio
from flows.compiler import FlowCompiler

FILM = STUDIO_BY_ID["feature-film-production-studio"]
MODEL = "openai/gpt-4.1-mini"


def _spec(rigor: str = "full_studio") -> WorkflowSpec:
    graph = build_studio_graph(FILM, rigor, model=MODEL, director_model=MODEL)  # type: ignore[arg-type]
    return WorkflowSpec(id=uuid4(), tenant_id=uuid4(), workspace_id=uuid4(), name="Film", version=1,
                        nodes=tuple(graph.nodes), edges=tuple(graph.edges), layout=graph.layout, modes=graph.modes)


def test_the_film_studio_is_a_fifty_agent_production_with_the_departments_of_a_real_film() -> None:
    spec = FlowCompiler.validate(_spec())
    crews = {node.id: node for node in spec.nodes if isinstance(node, CrewNodeSpec)}
    assert {"writers_room", "previs", "art", "camera", "sound", "vfx", "production", "qa", "release"} <= set(crews)
    assert sum(len(crew.agents) for crew in crews.values()) + 2 * sum(isinstance(node, AutoGenSandboxNodeSpec) for node in spec.nodes) == 50
    assert {node.id for node in spec.nodes if isinstance(node, AutoGenSandboxNodeSpec)} == {"edit_assembly", "delivery_pack"}
    roles = {agent.role for crew in crews.values() for agent in crew.agents}
    assert {"Director", "Director of Photography", "Production Designer", "Composer", "VFX Supervisor", "Line Producer", "Social Media Manager"} <= roles


def test_the_smaller_rigors_keep_the_core_of_the_production() -> None:
    standard = FlowCompiler.validate(_spec("standard"))
    ids = {node.id for node in standard.nodes}
    assert {"writers_room", "previs", "edit_assembly", "qa", "release"} <= ids and not {"camera", "sound", "vfx"} & ids


def test_only_teams_that_publish_declare_channels_and_the_declaration_survives_a_round_trip() -> None:
    declared = {blueprint.id: build_studio_graph(blueprint, "full_studio", model=MODEL, director_model=MODEL).modes.channels for blueprint in STUDIO_BLUEPRINTS}
    publishing = {"feature-film-production-studio", "marketing-social-publishing-studio"}
    assert all(declared[blueprint_id] == ("tiktok", "facebook", "youtube") for blueprint_id in publishing)
    assert all(channels == () for blueprint_id, channels in declared.items() if blueprint_id not in publishing)
    spec = _spec()
    assert WorkflowSpec.model_validate(spec.model_dump(mode="json")).modes.channels == ("tiktok", "facebook", "youtube")
    assert WorkflowModesSpec().channels == ()  # specs saved before channels existed stay valid
    with pytest.raises(ValueError):
        WorkflowModesSpec(channels=("myspace",))  # type: ignore[arg-type]


def test_the_release_team_prepares_per_channel_packages_and_never_claims_to_have_published() -> None:
    crew = next(node for node in _spec().nodes if node.id == "release")
    assert isinstance(crew, CrewNodeSpec)
    social = next(task for task in crew.tasks if task.id == "release_social_media_manager_task")
    assert "TikTok" in social.description and "YouTube" in social.description and "Facebook" in social.description and "without publishing" in social.description
    rules = {rule.pattern: rule.rule for rule in _spec().modes.path_rules}
    assert "never state that anything was posted" in rules["release/**"]


def test_the_film_template_is_in_the_gallery_and_requests_for_a_film_build_this_studio() -> None:
    assert TEMPLATE_BY_ID["feature-film-production-studio"].modes.channels
    for prompt in ("Make a feature film about a lighthouse keeper", "Tạo một bộ phim ngắn về Sài Gòn", "Sản xuất phim điện ảnh hành động", "Build a movie studio pipeline for a thriller"):
        found = detect_studio(prompt)
        assert found is not None and found.domain == "film", prompt
    for prompt in ("Create a documentary video campaign for the museum", "Make a documentary film about the museum", "Tạo video trailer quảng cáo cho phim mới"):
        found = detect_studio(prompt)
        assert found is not None and found.domain == "video", prompt
    found = detect_studio("Tạo một bộ phim ngắn 5 phút về người giữ hải đăng, có kịch bản, quay phim, nhạc phim và đăng trailer lên TikTok/YouTube")
    assert found is not None and found.domain == "film"
    found = detect_studio("Make a film")
    assert found is not None and found.domain == "film"
    assert detect_studio("Build a web app with a feature flag service").domain == "software"  # type: ignore[union-attr]
