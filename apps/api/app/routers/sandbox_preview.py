"""Short-lived, port-scoped preview capabilities. No application JWT reaches the iframe."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth.context import _secret
from app.routers.sandboxes import BUILD, SandboxRoute, _computer_context
from app.routers.common import get_services
from nexus_computer_sandbox import ComputerAccess

router = APIRouter(route_class=SandboxRoute, prefix="/api/v1/sandboxes", tags=["sandbox-previews"])


class PreviewRequest(BaseModel):
    port: int = Field(ge=1024, le=65535)


def preview_ticket(access: ComputerAccess, computer_id: UUID, port: int) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"tenant": str(access.tenant_id), "workspace": str(access.workspace_id), "computer": str(computer_id), "run": str(access.run_id) if access.run_id else None, "bot": str(access.bot_id) if access.bot_id else None, "port": port, "expires": int(time.time()) + 600}).encode()).rstrip(b"=").decode()
    signature = hmac.new(_secret(), b"nexus-preview:" + body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_preview(ticket: str) -> tuple[ComputerAccess, UUID, int]:
    try:
        if len(ticket) > 2048:
            raise ValueError("Invalid preview capability")
        body, signature = ticket.split(".")
        expected = hmac.new(_secret(), b"nexus-preview:" + body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid preview signature")
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(data["expires"]) <= time.time() or int(data["expires"]) > time.time() + 600 or not 1024 <= int(data["port"]) <= 65535:
            raise ValueError("Preview expired")
        access = ComputerAccess(UUID(data["tenant"]), UUID(data["workspace"]), UUID(data["bot"]) if data["bot"] else None, UUID(data["run"]) if data["run"] else None)
        return access, UUID(data["computer"]), int(data["port"])
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(403, "Preview capability is invalid or expired") from error


@router.post("/{computer_id}/preview")
async def create_preview(computer_id: UUID, body: PreviewRequest, request: Request, context: BUILD) -> dict[str, Any]:
    access, _ = await _computer_context(request, context, computer_id)
    handle, provider = await get_services(request).interactive.provider(access, computer_id)
    await provider.owned_port(handle, body.port)
    ticket = preview_ticket(access, computer_id, body.port)
    return {"url": f"/api/v1/sandboxes/preview/{ticket}/", "expires_in": 600, "port": body.port}


@router.api_route("/preview/{ticket}/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
async def proxy_preview(ticket: str, path: str, request: Request) -> Response:
    access, computer_id, port = verify_preview(ticket)
    service = get_services(request).interactive
    handle, provider = await service.provider(access, computer_id)
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(413, "Preview request exceeds 2 MiB")
    result = await provider.preview_request(handle, port, "/" + path + ("?" + request.url.query if request.url.query else ""), request.method, {**dict(request.headers), "accept-encoding": "identity"}, body or None)
    headers = {entry["name"].lower(): entry["value"] for entry in result["headers"] if entry["name"].lower() not in {"content-length", "set-cookie", "location", "access-control-allow-credentials", "access-control-allow-origin"}}
    content = base64.b64decode(result["body"])
    content_type = headers.get("content-type", "")
    prefix = f"/api/v1/sandboxes/preview/{ticket}/"
    if any(kind in content_type for kind in ("text/html", "javascript", "text/css")):
        text = content.decode("utf-8", errors="replace")
        if "text/html" in content_type:  # only URL-bearing attributes; script bodies keep their string literals
            text = re.sub(r'''(\b(?:src|href|action|poster)\s*=\s*)(["'])(/(?!/)[^"'\s]*)\2''', lambda m: m[1] + m[2] + (m[3] if m[3].startswith(prefix) else prefix + m[3].lstrip("/")) + m[2], text)
        elif "text/css" in content_type:
            text = re.sub(r'''(url\(\s*)(["']?)(/(?!/)[^"')\s]*)\2''', lambda m: m[1] + m[2] + (m[3] if m[3].startswith(prefix) else prefix + m[3].lstrip("/")) + m[2], text)
        content = text.encode()
        headers.pop("content-encoding", None)
    location = next((entry["value"] for entry in result["headers"] if entry["name"].lower() == "location"), None)
    if location:
        if not location.startswith("/") or location.startswith("//"):
            raise HTTPException(403, "External preview redirects are blocked")
        headers["location"] = prefix + location.lstrip("/")
    headers.update({"cache-control": "no-store", "referrer-policy": "no-referrer", "x-content-type-options": "nosniff", "access-control-allow-origin": "null", "content-security-policy": "sandbox allow-scripts allow-forms allow-downloads; frame-ancestors 'self'"})
    return Response(content, status_code=int(result["status"]), headers=headers)
