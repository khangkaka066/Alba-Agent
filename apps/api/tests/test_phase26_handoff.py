"""Phase 26: files handed from one agent team to the next inside a workspace."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.context import TenantContext
from app.handoff import MAX_EXCERPTS, MAX_FILES, carry_upstream, copy_sources, describe_for_architect, resolve_sources, safe_name
from app.models import WorkflowRun
from app.models.scope import scoped_session
from app.routers import artifacts
from flows.compiler import mount_upstream
from flows.state import WorkflowState
from nexus_core_schema.artifacts import artifact_directory

TENANT, WORKSPACE = uuid4(), uuid4()
CONTEXT = TenantContext(TENANT, WORKSPACE, uuid4(), "owner")


def _run(root: Path, files: dict[str, bytes]) -> UUID:
    run_id = uuid4()
    directory = artifact_directory(TENANT, WORKSPACE, run_id)
    for name, content in files.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(content)
    return run_id


def test_a_handed_over_file_is_checked_described_and_copied_byte_for_byte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    video = bytes(range(256)) * 400
    first = _run(tmp_path, {"final_video.mp4": video, "story/script.md": b"# Script\nA lighthouse keeper waits for a ship."})
    second = _run(tmp_path, {"script.md": b"Another script"})
    sources = resolve_sources([(first, "final_video.mp4"), (first, "story/script.md"), (second, "script.md"), (first, "final_video.mp4")], CONTEXT, {first, second})
    assert [source.name for source in sources] == ["final_video.mp4", "script.md", "script_2.md"], "duplicates are dropped and equal names stay distinct"
    assert [source.excerpt is not None for source in sources] == [False, True, True]
    assert sources[1].excerpt is not None and sources[1].excerpt.startswith("# Script") and sources[0].mime_type == "video/mp4"

    note = describe_for_architect(sources)
    assert "final_video.mp4 (video/mp4" in note and "A lighthouse keeper" in note and "do not recreate" in note and len(note) <= 4000
    assert describe_for_architect([]) == ""

    target = uuid4()
    entries = copy_sources(CONTEXT, sources, target)
    copied = artifact_directory(TENANT, WORKSPACE, target) / ".upstream"
    assert (copied / "final_video.mp4").read_bytes() == video
    assert entries[0] == {"name": "final_video.mp4", "source_run_id": str(first), "source_filename": "final_video.mp4", "path": ".upstream/final_video.mp4",
                          "size_bytes": len(video), "mime_type": "video/mp4", "excerpt": None}
    for path in artifact_directory(TENANT, WORKSPACE, first).rglob("*"):  # deleting the source later must not break the new team
        if path.is_file():
            path.unlink()
    assert (copied / "final_video.mp4").is_file() and (copied / "script.md").read_text().startswith("# Script")

    again = uuid4()
    kept = carry_upstream(CONTEXT, target, again, entries)
    assert [item["name"] for item in kept] == ["final_video.mp4", "script.md", "script_2.md"]
    assert (artifact_directory(TENANT, WORKSPACE, again) / ".upstream" / "final_video.mp4").read_bytes() == video


def test_references_that_leave_the_workspace_or_the_run_folder_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    mine = _run(tmp_path, {"a.md": b"a", "sub/b.md": b"b"})
    foreign = uuid4()
    (artifact_directory(TENANT, WORKSPACE, foreign)).mkdir(parents=True)
    (artifact_directory(TENANT, WORKSPACE, foreign) / "secret.md").write_text("not yours")
    (artifact_directory(TENANT, WORKSPACE, mine) / "link.md").symlink_to(tmp_path)
    cases: list[tuple[list[tuple[UUID, str]], int]] = [
        ([(foreign, "secret.md")], 404),  # not one of this workspace's runs
        ([(mine, "../" + str(foreign) + "/secret.md")], 422), ([(mine, "/etc/passwd")], 422), ([(mine, ".upstream/a.md")], 422),
        ([(mine, "sub\\b.md")], 422), ([(mine, "link.md")], 422), ([(mine, "missing.md")], 404), ([(mine, "sub")], 404),
        ([(mine, f"f{index}.md") for index in range(MAX_FILES + 1)], 422),
    ]
    for references, code in cases:
        with pytest.raises(HTTPException) as refused:
            resolve_sources(references, CONTEXT, {mine})
        assert refused.value.status_code == code, references[:1]
    assert [source.name for source in resolve_sources([(mine, "sub/b.md")], CONTEXT, {mine})] == ["b.md"]
    assert safe_name("../../etc/pass wd?.md") == "pass_wd_.md" and safe_name("...") == "file"


def test_only_the_first_few_files_carry_a_text_excerpt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = _run(tmp_path, {f"note{index}.md": f"text {index} ".encode() * 2000 for index in range(MAX_EXCERPTS + 3)})
    sources = resolve_sources([(run_id, f"note{index}.md") for index in range(MAX_EXCERPTS + 3)], CONTEXT, {run_id})
    assert [source.excerpt is not None for source in sources] == [True] * MAX_EXCERPTS + [False] * 3
    assert all(source.excerpt is None or len(source.excerpt) <= 3000 for source in sources)


def test_the_sandbox_gets_small_handed_over_files_and_hears_about_the_large_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    run_id = uuid4()
    folder = artifact_directory(TENANT, WORKSPACE, run_id) / ".upstream"
    folder.mkdir(parents=True)
    (folder / "script.md").write_text("small")
    (folder / "video.mp4").write_bytes(b"v" * 2_000_000)
    (folder / "table.csv").write_bytes(b"c" * 900_000)
    entries = [{"name": "video.mp4", "size_bytes": 2_000_000, "mime_type": "video/mp4", "source_run_id": "s"},
               {"name": "table.csv", "size_bytes": 900_000, "mime_type": "text/csv", "source_run_id": "s"},
               {"name": "script.md", "size_bytes": 5, "mime_type": "text/markdown", "source_run_id": "s"},
               {"name": "../escape.md", "size_bytes": 1, "mime_type": "text/markdown", "source_run_id": "s"}]
    state = WorkflowState(id=run_id, run_id=run_id, workflow_id=uuid4(), tenant_id=TENANT, workspace_id=WORKSPACE, upstream_artifacts=entries)
    files: dict[str, bytes] = {"dataset.csv": b"x" * 100_000}
    described = {item["name"]: item["mounted_path"] for item in mount_upstream(state, files)}
    assert described == {"script.md": "upstream/script.md", "table.csv": "upstream/table.csv", "video.mp4": None, "../escape.md": None}
    assert sum(len(content) for content in files.values()) <= 1_048_576 and "upstream/video.mp4" not in files


def test_the_picker_search_shows_this_workspaces_files_and_no_one_elses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    required = ("NEXUS_TEST_DATABASE_URL", "NEXUS_TEST_APP_DATABASE_URL")
    if any(name not in os.environ for name in required):
        pytest.skip("PostgreSQL with the runtime role is required")
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))

    async def check() -> None:
        tenant, workspace, other_tenant, other_workspace = uuid4(), uuid4(), uuid4(), uuid4()
        workflow, other_workflow, film_run, report_run, hidden_run = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        admin, runtime = create_async_engine(os.environ["NEXUS_TEST_DATABASE_URL"]), create_async_engine(os.environ["NEXUS_TEST_APP_DATABASE_URL"])
        request = cast(Request, SimpleNamespace(app=cast(FastAPI, SimpleNamespace(state=SimpleNamespace(services=SimpleNamespace(engine=runtime))))))
        try:
            async with admin.begin() as connection:
                for t, w, wf, name in ((tenant, workspace, workflow, "Lighthouse film"), (other_tenant, other_workspace, other_workflow, "Other film")):
                    await connection.execute(text("INSERT INTO tenants (id, name) VALUES (:id, 'Pick')"), {"id": t})
                    await connection.execute(text("INSERT INTO workspaces (id, tenant_id, name) VALUES (:id, :t, 'Pick')"), {"id": w, "t": t})
                    await connection.execute(text("INSERT INTO workflows (id, tenant_id, workspace_id, name, version, spec) VALUES (:id, :t, :w, :n, 1, '{}'::jsonb)"), {"id": wf, "t": t, "w": w, "n": name})
            async with scoped_session(runtime, tenant, workspace) as session:
                session.add_all([WorkflowRun(id=film_run, tenant_id=tenant, workspace_id=workspace, workflow_id=workflow, status="completed"),
                                 WorkflowRun(id=report_run, tenant_id=tenant, workspace_id=workspace, workflow_id=workflow, status="failed")])
            async with scoped_session(runtime, other_tenant, other_workspace) as session:
                session.add(WorkflowRun(id=hidden_run, tenant_id=other_tenant, workspace_id=other_workspace, workflow_id=other_workflow, status="completed"))
            for t, w, run, name in ((tenant, workspace, film_run, "final_video.mp4"), (tenant, workspace, report_run, "report.md"), (other_tenant, other_workspace, hidden_run, "secret_plan.md")):
                directory = artifact_directory(t, w, run)
                directory.mkdir(parents=True)
                (directory / name).write_bytes(b"data")
            context = TenantContext(tenant, workspace, uuid4(), "owner")
            everything = await artifacts.search_artifacts(request, context, "", 30)
            assert {(item["filename"], item["run_name"]) for item in everything} == {("final_video.mp4", "Lighthouse film"), ("report.md", "Lighthouse film")}
            assert [item["filename"] for item in await artifacts.search_artifacts(request, context, "VIDEO", 30)] == ["final_video.mp4"]
            assert len(await artifacts.search_artifacts(request, context, "lighthouse", 1)) == 1, "the task name matches too, and the limit holds"
            assert await artifacts.search_artifacts(request, context, "secret", 30) == []
        finally:
            await admin.dispose()
            await runtime.dispose()

    asyncio.run(check())
