"""Workspace-scoped file locations and safe metadata for run deliverables."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from urllib.parse import quote
from typing import Any
from uuid import UUID


MEDIA_TYPES = {
    ".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".md": "text/markdown",
}


def artifact_directory(tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> Path:
    root = Path(os.environ.get("NEXUS_ARTIFACTS_DIR", os.environ.get("NEXUS_ARTIFACT_ROOT", "/tmp/nexus-artifacts")))
    return root / str(tenant_id) / str(workspace_id) / str(run_id)


def artifact_file(directory: Path, filename: str) -> Path:
    """Resolve a run-relative artifact path such as ``report.md`` or ``design/gdd.md``."""
    parts = filename.split("/") if filename else []
    if (
        not parts or len(parts) > 8 or "\\" in filename or Path(filename).is_absolute()
        or any(not part or part in {".", ".."} or part.startswith(".") for part in parts)
    ):
        raise ValueError("Invalid artifact filename")
    root = directory.resolve()
    candidate = directory.joinpath(*parts)
    current = directory
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Artifact path escapes the run directory")
    if root not in candidate.resolve().parents:
        raise ValueError("Artifact path escapes the run directory")
    return candidate


def list_artifacts(
    tenant_id: UUID, workspace_id: UUID, run_id: UUID,
    node_outputs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    directory = artifact_directory(tenant_id, workspace_id, run_id)
    if not directory.is_dir():
        return []
    producers: dict[str, str] = {}
    for node_id, output in (node_outputs or {}).items():
        if not isinstance(output, dict):
            continue
        for field in ("artifact_filename", "report_filename", "artifact"):
            filename = output.get(field)
            if isinstance(filename, str):
                producers[filename] = node_id
        contract = output.get("artifact_contract")
        if isinstance(contract, dict):
            for filename in (*contract.get("verified", ()), *contract.get("recovered", ())):
                if isinstance(filename, str):
                    producers.setdefault(filename, node_id)
    root = directory.resolve()
    result: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if len(result) >= 200:
            break
        relative = path.relative_to(directory)
        if any(part.startswith(".") for part in relative.parts) or path.is_symlink() or not path.is_file():
            continue
        if root not in path.resolve().parents:
            continue
        name = relative.as_posix()
        mime_type = MEDIA_TYPES.get(path.suffix.lower(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        url = f"/api/v1/runs/{run_id}/artifacts/{quote(name, safe='/')}"
        result.append({
            "filename": name, "mime_type": mime_type, "size_bytes": path.stat().st_size,
            "download_url": url, "preview_url": url, "created_by_node": producers.get(name),
        })
    return result
