#!/usr/bin/env python3
"""Issue an offline Enterprise license JWT using an operator-held Ed25519 key."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _segment(value: dict[str, object]) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def issue_license(
    private_key_path: Path, subject: str, expires_in_days: int,
    features: set[str], tenant_id: UUID | None,
) -> str:
    if not subject.strip() or not 1 <= expires_in_days <= 3650:
        raise ValueError("Subject and expiration period are invalid")
    if not features or not features <= {"multi_workspace", "sso", "audit_logs"}:
        raise ValueError("At least one supported Enterprise feature is required")
    loaded = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError("License signing key must be Ed25519")
    issued = int(time.time())
    claims: dict[str, object] = {
        "iss": "nexus-license", "aud": "nexus-enterprise", "sub": subject.strip(),
        "iat": issued, "nbf": issued, "exp": issued + expires_in_days * 86_400,
        "features": sorted(features),
    }
    if tenant_id is not None:
        claims["tenant_id"] = str(tenant_id)
    head, body = _segment({"alg": "EdDSA", "typ": "JWT"}), _segment(claims)
    signing_input = f"{head}.{body}".encode()
    return f"{head}.{body}.{base64.urlsafe_b64encode(loaded.sign(signing_input)).rstrip(b'=').decode()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path, help="Path to protected Ed25519 PEM key; key contents are never printed")
    parser.add_argument("--subject", required=True, help="Customer or license owner identifier")
    parser.add_argument("--expires-in-days", required=True, type=int)
    parser.add_argument("--feature", action="append", choices=("multi_workspace", "sso", "audit_logs"), required=True)
    parser.add_argument("--tenant-id", type=UUID, help="Optional tenant binding; omit for a key usable by one self-hosted installation")
    args = parser.parse_args()
    try:
        print(issue_license(args.private_key, args.subject, args.expires_in_days, set(args.feature), args.tenant_id))
    except (OSError, ValueError, TypeError) as error:
        print(f"Could not issue Enterprise license: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
