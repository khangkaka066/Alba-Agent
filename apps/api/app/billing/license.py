"""Offline verification for Ed25519-signed enterprise license JWTs."""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm


@dataclass(frozen=True)
class EnterpriseLicense:
    subject: str
    issued_at: int
    expires_at: int
    features: frozenset[str]
    tenant_id: UUID | None


def _b64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _public_key(value: str) -> Ed25519PublicKey:
    if value.startswith("-----BEGIN PUBLIC KEY-----"):
        loaded = serialization.load_pem_public_key(value.encode())
        if not isinstance(loaded, Ed25519PublicKey):
            raise ValueError("NEXUS_LICENSE_PUBLIC_KEY must be Ed25519")
        return loaded
    raw = base64.b64decode(value, validate=True)
    if len(raw) != 32:
        raise ValueError("NEXUS_LICENSE_PUBLIC_KEY must contain a 32-byte public key")
    return Ed25519PublicKey.from_public_bytes(raw)


def verify_license(token: str | None = None, *, now: int | None = None) -> EnterpriseLicense:
    license_token = token if token is not None else os.environ.get("NEXUS_LICENSE_KEY", "")
    public_key = os.environ.get("NEXUS_LICENSE_PUBLIC_KEY", "")
    if not license_token or not public_key:
        raise ValueError("Enterprise license or verification key is not configured")
    try:
        head, body, signature = license_token.split(".")
        if len(license_token) > 8192:
            raise ValueError("License token is too large")
        header = json.loads(_b64url(head))
        claims = json.loads(_b64url(body))
        if header != {"alg": "EdDSA", "typ": "JWT"}:
            raise ValueError("Unsupported license algorithm")
        _public_key(public_key).verify(_b64url(signature), f"{head}.{body}".encode())
        current = int(time.time()) if now is None else now
        issued = claims["iat"]
        expires = claims["exp"]
        not_before = claims.get("nbf", issued)
        if not all(isinstance(value, int) for value in (issued, expires, not_before)):
            raise ValueError("License timestamps must be integers")
        if claims.get("iss") != "nexus-license" or claims.get("aud") != "nexus-enterprise":
            raise ValueError("License issuer or audience is invalid")
        if issued > current + 60 or not_before > current or expires <= current or expires <= issued:
            raise ValueError("Enterprise license is expired or not yet valid")
        raw_features = claims.get("features")
        if not isinstance(raw_features, list) or not all(isinstance(feature, str) for feature in raw_features):
            raise ValueError("Enterprise license features are invalid")
        allowed = {"multi_workspace", "sso", "audit_logs"}
        features = frozenset(raw_features)
        if not features <= allowed:
            raise ValueError("Enterprise license contains an unknown feature")
        tenant = UUID(claims["tenant_id"]) if claims.get("tenant_id") else None
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise ValueError("Enterprise license subject is missing")
        return EnterpriseLicense(subject, issued, expires, features, tenant)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, InvalidSignature, UnsupportedAlgorithm) as error:
        raise ValueError("Enterprise license verification failed") from error


def licensed_feature(feature: str, tenant_id: UUID | None = None) -> bool:
    try:
        license_data = verify_license()
    except ValueError:
        return False
    return feature in license_data.features and (license_data.tenant_id is None or license_data.tenant_id == tenant_id)
