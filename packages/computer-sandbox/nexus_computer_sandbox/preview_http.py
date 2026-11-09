"""Bounded loopback HTTP fetcher, executed inside a Docker computer for previews."""
from __future__ import annotations

import base64
import http.client
import json
import sys
from typing import Any


def request_local(port: int, path: str, method: str, headers: dict[str, str], body: bytes | None) -> dict[str, Any]:
    if not 1024 <= port <= 65535 or not path.startswith("/") or method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}:
        raise ValueError("Invalid preview request")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        filtered = {key: value for key, value in headers.items() if key.lower() not in {"host", "authorization", "cookie", "connection", "upgrade", "transfer-encoding", "content-length"}}
        connection.request(method, path, body=body, headers={**filtered, "Host": f"localhost:{port}"})
        response = connection.getresponse()
        content = response.read(16 * 1024 * 1024 + 1)
        if len(content) > 16 * 1024 * 1024:
            raise ValueError("Preview response exceeds 16 MiB")
        return {"status": response.status, "headers": [{"name": key, "value": value} for key, value in response.getheaders() if key.lower() not in {"set-cookie", "connection", "transfer-encoding"}], "body": base64.b64encode(content).decode()}
    finally:
        connection.close()


if __name__ == "__main__":
    data = json.load(sys.stdin)
    print(json.dumps(request_local(int(data["port"]), data["path"], data["method"], data.get("headers", {}), base64.b64decode(data["body"]) if data.get("body") else None)))
