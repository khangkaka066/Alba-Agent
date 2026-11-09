"""DNS-pinned public HTTP transport for the otherwise networkless sandbox browser."""
from __future__ import annotations

import base64
import http.client
import ipaddress
import socket
import ssl
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE = 16 * 1024 * 1024
DROP_HEADERS = frozenset({"host", "connection", "proxy-authorization", "proxy-connection", "transfer-encoding", "content-length", "upgrade"})


def public_fetch(url: str, method: str, headers: dict[str, str], body: bytes | None = None) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise PermissionError("Browser requests require a public HTTP(S) URL")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise PermissionError("Private addresses and metadata endpoints are blocked")
    address = str(addresses[0][4][0])
    host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    class Connection(http.client.HTTPConnection):
        def connect(self) -> None:
            raw = socket.create_connection((address, port), 15)
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if parsed.scheme == "https" else raw
    connection = Connection(host, port, timeout=15)
    try:
        filtered = {key: value for key, value in headers.items() if key.lower() not in DROP_HEADERS}
        connection.request(method, parsed.path + ("?" + parsed.query if parsed.query else "") or "/", body=body, headers={**filtered, "Host": parsed.netloc, "Connection": "close"})
        response = connection.getresponse()
        content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise ValueError("Browser response exceeds 16 MiB")
        return {"status": response.status, "headers": [{"name": key, "value": value} for key, value in response.getheaders() if key.lower() not in {"transfer-encoding", "connection"}], "body": base64.b64encode(content).decode()}
    finally:
        connection.close()
