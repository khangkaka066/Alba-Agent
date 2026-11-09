"""Bounded binary attachments selected by the user, scoped to their workspace."""
from __future__ import annotations

import json
import mimetypes
import shutil
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from app.auth.context import TenantContext, require_role
from app.handoff import MAX_FILES, Source, TEXT_SUFFIXES, safe_name
from nexus_core_schema.artifacts import artifact_directory

router = APIRouter(prefix="/api/v1/uploads", tags=["attachments"])
BUILD = Annotated[TenantContext, Depends(require_role("builder", "write"))]
READ = Annotated[TenantContext, Depends(require_role("viewer", "read"))]
MAX_UPLOAD_BYTES = 20_000_000
MAX_BATCH_BYTES = 50_000_000


def upload_directory(context: TenantContext, upload_id: UUID) -> Path:
    workspace = artifact_directory(context.tenant_id, context.workspace_id, upload_id).parent
    directory = workspace / ".uploads" / str(upload_id)
    for path in (workspace.parent, workspace, directory.parent, directory):
        if path.is_symlink():
            raise HTTPException(404, "Attachment is not visible in this workspace")
    return directory


def resolve_uploads(ids: list[UUID], context: TenantContext, occupied: set[str] | None = None) -> list[Source]:
    unique = list(dict.fromkeys(ids))
    if len(unique) > MAX_FILES:
        raise HTTPException(422, f"At most {MAX_FILES} attachments can be sent at once")
    taken = set(occupied or ())
    sources: list[Source] = []
    for upload_id in unique:
        directory = upload_directory(context, upload_id)
        metadata = directory / "metadata.json"
        path = directory / "content"
        if metadata.is_symlink() or path.is_symlink() or not metadata.is_file() or not path.is_file():
            raise HTTPException(404, "Attachment is not visible in this workspace")
        try:
            record = json.loads(metadata.read_text(encoding="utf-8"))
            filename, mime = str(record["filename"]), str(record["mime_type"])
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(404, "Attachment metadata is unavailable") from error
        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Each attachment must be at most 20 MB")
        name = safe_name(filename)
        stem, dot, suffix = name.partition(".")
        index = 1
        while name in taken:
            index += 1
            name = f"{stem}_{index}{dot}{suffix}"
        taken.add(name)
        excerpt = None
        if Path(filename).suffix.lower() in TEXT_SUFFIXES:
            with path.open(encoding="utf-8", errors="replace") as handle:
                excerpt = handle.read(3000)
        sources.append(Source(None, filename, path, name, size, mime, excerpt, upload_id))
    if sum(source.size_bytes for source in sources) > MAX_BATCH_BYTES:
        raise HTTPException(413, "Attachments exceed the 50 MB message limit")
    return sources


@router.post("", status_code=201)
async def upload_file(request: Request, context: BUILD, filename: Annotated[str, Query(min_length=1, max_length=240)]) -> dict[str, Any]:
    if filename in {".", ".."} or not filename.strip() or any(char in filename for char in ("/", "\\")) or any(ord(char) < 32 or ord(char) == 127 for char in filename):
        raise HTTPException(422, "Choose a plain file name without paths or control characters")
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Each attachment must be at most 20 MB")
        except ValueError as error:
            raise HTTPException(400, "Invalid attachment size") from error
    upload_id = uuid4()
    directory = upload_directory(context, upload_id)
    directory.mkdir(parents=True, mode=0o700)
    ready = False
    try:
        size = 0
        with (directory / "content").open("xb") as handle:
            (directory / "content").chmod(0o600)
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Each attachment must be at most 20 MB")
                handle.write(chunk)
        record = {"id": str(upload_id), "filename": filename, "size_bytes": size,
                  "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream"}
        (directory / "metadata.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        (directory / "metadata.json").chmod(0o600)
        ready = True
        return record
    finally:
        if not ready:
            shutil.rmtree(directory)


@router.get("/{upload_id}")
async def download_upload(upload_id: UUID, context: READ) -> FileResponse:
    source = resolve_uploads([upload_id], context)[0]
    return FileResponse(source.path, media_type="application/octet-stream", filename=source.filename,
                        headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/{upload_id}", status_code=204)
async def delete_upload(upload_id: UUID, context: BUILD) -> Response:
    resolve_uploads([upload_id], context)
    shutil.rmtree(upload_directory(context, upload_id))
    return Response(status_code=204)
