"""Import reviewed OpenAPI 3.1 JSON operations as scoped tools."""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urlsplit

import httpx

from .hub import ToolBinding, UnifiedToolHub

ApprovalGuard = Callable[[str, str, dict[str, Any]], Awaitable[None]]
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")
SAFE_NAME = re.compile(r"[^a-z0-9_]+")


def _resolve_reference(value: Any, document: dict[str, Any], depth: int = 0) -> Any:
    if depth > 16:
        raise ValueError("OpenAPI reference nesting is too deep")
    if isinstance(value, list):
        return [_resolve_reference(item, document, depth + 1) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValueError("OpenAPI imports may only use local references")
        target: Any = document
        for raw in reference[2:].split("/"):
            key = raw.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or key not in target:
                raise ValueError("OpenAPI reference target does not exist")
            target = target[key]
        merged = {**target, **{key: child for key, child in value.items() if key != "$ref"}}
        return _resolve_reference(merged, document, depth + 1)
    return {key: _resolve_reference(child, document, depth + 1) for key, child in value.items()}


class OpenAPIImporter:
    def __init__(
        self,
        hub: UnifiedToolHub,
        allowed_origins: frozenset[str],
        client: httpx.AsyncClient,
        approval_guard: ApprovalGuard | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._hub = hub
        self._allowed_origins = allowed_origins
        self._client = client
        self._approval_guard = approval_guard
        self._headers = dict(headers or {})

    def import_spec(self, specification: dict[str, Any]) -> tuple[str, ...]:
        if len(json.dumps(specification)) > 1_048_576 or not str(specification.get("openapi", "")).startswith("3.1."):
            raise ValueError("Import requires a bounded OpenAPI 3.1 JSON specification")
        servers = specification.get("servers", [])
        if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
            raise ValueError("OpenAPI specification requires an HTTPS server")
        base_url = str(servers[0].get("url", ""))
        parsed = urlsplit(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or origin not in self._allowed_origins:
            raise ValueError("OpenAPI server origin is not approved")
        paths = specification.get("paths", {})
        if not isinstance(paths, dict):
            raise ValueError("OpenAPI paths must be an object")
        names: list[str] = []
        for path, path_item in paths.items():
            if not isinstance(path, str) or not path.startswith("/") or ".." in path.split("/") or not isinstance(path_item, dict):
                raise ValueError("OpenAPI path is invalid")
            for method, raw in path_item.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                if not isinstance(raw, dict):
                    raise ValueError("OpenAPI operation is invalid")
                operation = _resolve_reference(raw, specification)
                operation_id = operation.get("operationId")
                if not isinstance(operation_id, str) or not operation_id:
                    raise ValueError("OpenAPI operation requires operationId")
                name = "nexus_api_" + SAFE_NAME.sub("_", operation_id.lower()).strip("_")
                parameters = _resolve_reference(path_item.get("parameters", []) + operation.get("parameters", []), specification)
                if not isinstance(parameters, list):
                    raise ValueError("OpenAPI parameters must be a list")
                groups: dict[str, dict[str, Any]] = {"path": {}, "query": {}}
                required_groups: dict[str, list[str]] = {"path": [], "query": []}
                for parameter in parameters:
                    if not isinstance(parameter, dict) or parameter.get("in") not in groups:
                        raise ValueError("Only path and query OpenAPI parameters are supported")
                    location = parameter["in"]
                    key = parameter.get("name")
                    schema = parameter.get("schema")
                    if not isinstance(key, str) or not isinstance(schema, dict):
                        raise ValueError("OpenAPI parameter schema is missing")
                    groups[location][key] = schema
                    if parameter.get("required", False) or location == "path":
                        required_groups[location].append(key)
                if set(PATH_PARAMETER.findall(path)) != set(required_groups["path"]):
                    raise ValueError("OpenAPI path parameters do not match the route")
                properties: dict[str, Any] = {}
                required: list[str] = []
                for location in ("path", "query"):
                    if groups[location]:
                        properties[location] = {
                            "type": "object", "properties": groups[location],
                            "required": required_groups[location], "additionalProperties": False,
                        }
                        if required_groups[location]:
                            required.append(location)
                request_body = operation.get("requestBody")
                if request_body is not None:
                    request_body = _resolve_reference(request_body, specification)
                    content = request_body.get("content", {})
                    media = content.get("application/json") if isinstance(content, dict) else None
                    if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
                        raise ValueError("Only JSON OpenAPI request bodies are supported")
                    properties["body"] = _resolve_reference(media["schema"], specification)
                    if request_body.get("required", False):
                        required.append("body")
                schema = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
                operation_url = base_url.rstrip("/") + path
                http_method = method.upper()

                async def invoke(arguments: dict[str, Any], *, _url: str = operation_url, _method: str = http_method) -> Any:
                    url = PATH_PARAMETER.sub(
                        lambda match: quote(str(arguments.get("path", {})[match.group(1)]), safe=""), _url
                    )
                    if _method != "GET":
                        if self._approval_guard is None:
                            raise PermissionError("External write operations require an approval guard")
                        await self._approval_guard(_method, url, arguments)
                    response = await self._client.request(
                        _method, url, params=arguments.get("query"), json=arguments.get("body"),
                        headers=self._headers, follow_redirects=False,
                    )
                    response.raise_for_status()
                    if len(response.content) > 1_048_576:
                        raise ValueError("OpenAPI response exceeds the 1 MiB limit")
                    return response.json() if "json" in response.headers.get("content-type", "") else response.text

                self._hub.register(ToolBinding(
                    name=name, description="Call an approved workspace API operation",
                    input_schema=schema, invoke=invoke,
                ))
                names.append(name)
        return tuple(names)
