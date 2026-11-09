"""Binary attachment integrity, scope isolation, bounded uploads and execution handoff."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute

from app.auth.context import TenantContext
from app.handoff import copy_sources, resolve_sources, stage_computer_inputs
from app.routers import uploads
from flows.compiler import mount_upstream
from flows.state import WorkflowState
from nexus_core_schema.artifacts import artifact_directory


def context() -> TenantContext:
    return TenantContext(uuid4(), uuid4(), uuid4(), "owner")


def application(scope: TenantContext) -> FastAPI:
    app = FastAPI()
    app.include_router(uploads.router)
    for route in app.routes:
        if isinstance(route, APIRoute):
            for dependency in route.dependant.dependencies:
                if dependency.call is not None:
                    app.dependency_overrides[dependency.call] = lambda: scope
    return app


def test_binary_files_and_unicode_names_round_trip_without_corruption_or_cross_scope_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    scope = context()
    app = application(scope)
    binary = bytes(range(256)) * 8192  # Larger than the previous 1 MiB text-input limit.

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://nexus.test") as client:
            result = await client.post("/api/v1/uploads", params={"filename": "Báo cáo quý 4.pdf"}, content=binary)
            assert result.status_code == 201, result.text
            record = result.json()
            assert record["filename"] == "Báo cáo quý 4.pdf" and record["size_bytes"] == len(binary)
            upload_id = UUID(record["id"])
            response = await client.get(f"/api/v1/uploads/{upload_id}")
            assert response.content == binary and response.headers["content-type"] == "application/octet-stream"
            assert "attachment" in response.headers["content-disposition"] and response.headers["x-content-type-options"] == "nosniff"
            for foreign in (TenantContext(scope.tenant_id, uuid4(), scope.user_id, "owner"), context()):
                with pytest.raises(HTTPException) as denied:
                    uploads.resolve_uploads([upload_id], foreign)
                assert denied.value.status_code == 404
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(foreign)), base_url="http://nexus.test") as other:
                    assert (await other.delete(f"/api/v1/uploads/{upload_id}")).status_code == 404
            sources = uploads.resolve_uploads([upload_id], scope)
            target_run = uuid4()
            entries = copy_sources(scope, sources, target_run)
            target = artifact_directory(scope.tenant_id, scope.workspace_id, target_run)
            assert (target / ".upstream" / sources[0].name).read_bytes() == binary
            state = WorkflowState(id=target_run, run_id=target_run, workflow_id=uuid4(), tenant_id=scope.tenant_id, workspace_id=scope.workspace_id, upstream_artifacts=entries)
            files: dict[str, bytes] = {}
            described = mount_upstream(state, files)
            assert files[f"upstream/{sources[0].name}"] == binary and described[0]["mounted_path"] is not None
            staged: dict[str, bytes] = {}
            async def upload(path: str, content: bytes) -> None:
                staged[path] = content
            await stage_computer_inputs(target, upload)
            assert staged == files, "Native tools and sandbox nodes must receive identical uploaded bytes"
            assert (await client.delete(f"/api/v1/uploads/{upload_id}")).status_code == 204
            assert (await client.get(f"/api/v1/uploads/{upload_id}")).status_code == 404
            assert (target / ".upstream" / sources[0].name).read_bytes() == binary, "Removing the draft source cannot break an active run"
    asyncio.run(run())


def test_stream_size_limit_and_interrupted_uploads_leave_no_partial_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 10)
    scope = context()
    async def oversized() -> AsyncIterator[bytes]:
        yield b"123456"
        yield b"789012"
    async def interrupted() -> AsyncIterator[bytes]:
        yield b"123"
        raise RuntimeError("upload interrupted")
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(scope)), base_url="http://nexus.test") as client:
            assert (await client.post("/api/v1/uploads?filename=large.bin", content=oversized())).status_code == 413
            assert (await client.post("/api/v1/uploads?filename=large.bin", content=b"x" * 11)).status_code == 413
            with pytest.raises(RuntimeError, match="upload interrupted"):
                await client.post("/api/v1/uploads?filename=partial.bin", content=interrupted())
            for name in ("../secret.txt", "/etc/passwd", "a\\b.txt", "..", "a\x00.txt"):
                assert (await client.post("/api/v1/uploads", params={"filename": name}, content=b"x")).status_code == 422
            response = await client.post("/api/v1/uploads?filename=empty.txt", content=b"")
            assert response.status_code == 201 and response.json()["size_bytes"] == 0
            assert (await client.delete(f"/api/v1/uploads/{response.json()['id']}")).status_code == 204
        folder = uploads.upload_directory(scope, uuid4()).parent
        assert not list(folder.iterdir()), "Rejected uploads must not leave incomplete attachments"
    asyncio.run(run())


def test_file_names_collide_safely_and_symlinks_cannot_escape_the_upload_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ARTIFACTS_DIR", str(tmp_path))
    scope = context()
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(scope)), base_url="http://nexus.test") as client:
            records = [(await client.post("/api/v1/uploads?filename=note.txt", content=value)).json() for value in (b"first", b"second")]
            ids = [UUID(item["id"]) for item in records]
            sources = uploads.resolve_uploads([*ids, ids[0]], scope, {"note.txt"})
            assert [item.name for item in sources] == ["note_2.txt", "note_3.txt"] and [item.excerpt for item in sources] == ["first", "second"]
            directory = uploads.upload_directory(scope, ids[0])
            (directory / "content").unlink()
            (directory / "content").symlink_to(tmp_path / "secret")
            with pytest.raises(HTTPException) as denied:
                uploads.resolve_uploads([ids[0]], scope)
            assert denied.value.status_code == 404
            with pytest.raises(HTTPException) as denied_artifact:
                resolve_sources([(ids[1], "content")], scope, set())
            assert denied_artifact.value.status_code == 404, "An upload ID must never grant access through the run artifact API"
            monkeypatch.setattr(uploads, "MAX_BATCH_BYTES", 1)
            with pytest.raises(HTTPException) as too_large:
                uploads.resolve_uploads([ids[1]], scope)
            assert too_large.value.status_code == 413
    asyncio.run(run())


def test_upload_routes_require_authentication() -> None:
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=None)
    app.include_router(uploads.router)
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://nexus.test") as client:
            for method, path in (("POST", "/api/v1/uploads?filename=a.txt"), ("GET", f"/api/v1/uploads/{uuid4()}"), ("DELETE", f"/api/v1/uploads/{uuid4()}")):
                assert (await client.request(method, path, content=b"x" if method == "POST" else None)).status_code == 401
    asyncio.run(run())
