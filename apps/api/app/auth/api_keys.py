"""Issue and verify opaque service keys without storing plaintext."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets


def hash_service_key(value: str, pepper: bytes) -> str:
    if not value.startswith("nx-sk-") or len(pepper) < 32:
        raise ValueError("Invalid service key or server pepper")
    return hmac.new(pepper, value.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_service_key() -> tuple[str, str, str]:
    """Return plaintext once, a display prefix, and its HMAC for storage."""
    pepper = os.environ["NEXUS_API_KEY_PEPPER"].encode("utf-8")
    secret = "nx-sk-" + secrets.token_urlsafe(32)
    return secret, secret[:18], hash_service_key(secret, pepper)


def verify_service_key(candidate: str, stored_hash: str) -> bool:
    pepper = os.environ["NEXUS_API_KEY_PEPPER"].encode("utf-8")
    try:
        candidate_hash = hash_service_key(candidate, pepper)
    except ValueError:
        return False
    return hmac.compare_digest(candidate_hash, stored_hash)
