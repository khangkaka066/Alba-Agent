"""Workspace-scoped execution preferences, layered over mandatory sandbox protections."""
from __future__ import annotations

import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permission_preset: Literal["auto", "strict"] = "auto"
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    denied_domains: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("allowed_domains", "denied_domains")
    @classmethod
    def domains(cls, values: list[str]) -> list[str]:
        result = []
        for raw in values:
            value = raw.strip().lower()
            if not value:
                continue
            if "://" in value:
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                    raise ValueError("Enter a domain or an HTTP(S) URL without credentials")
                value = parsed.hostname or ""
            wildcard = value.startswith("*.")
            host = value[2:] if wildcard else value
            try:
                host = host.encode("idna").decode("ascii").rstrip(".")
            except UnicodeError as error:
                raise ValueError("Invalid network domain") from error
            if len(host) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
                raise ValueError("Enter domain names, one per line")
            normalized = ("*." if wildcard else "") + host
            if normalized not in result:
                result.append(normalized)
        return result

    def allows_url(self, url: str) -> bool:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
            if parsed.scheme.lower() not in {"http", "https"} or not host:
                return False
        except (ValueError, UnicodeError):
            return False
        def matches(pattern: str) -> bool:
            return host.endswith("." + pattern[2:]) if pattern.startswith("*.") else host == pattern
        return not any(matches(domain) for domain in self.denied_domains) and (not self.allowed_domains or any(matches(domain) for domain in self.allowed_domains))

    def check_tool(self, tool_id: str, payload: dict[str, Any]) -> None:
        # These restrictions apply to URL reads issued through managed tools. The OS sandbox,
        # private-address filters and sensitive-action approvals still apply independently.
        encoded = json.dumps(payload, ensure_ascii=False)
        for url in re.findall(r"https?://[^\s\"'<>]+", encoded, re.IGNORECASE):
            if not self.allows_url(url):
                raise PermissionError("This URL is blocked by the workspace network access rules")


def execution_key(tenant_id: UUID, workspace_id: UUID) -> str:
    return f"settings:execution:{tenant_id}:{workspace_id}"


async def load_execution_settings(redis: Redis, tenant_id: UUID, workspace_id: UUID) -> ExecutionSettings:
    saved = await redis.get(execution_key(tenant_id, workspace_id))
    return ExecutionSettings.model_validate_json(saved) if saved else ExecutionSettings()
