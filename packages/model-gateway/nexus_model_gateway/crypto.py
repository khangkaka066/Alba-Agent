"""Authenticated encryption for workspace-scoped provider credentials."""

from __future__ import annotations

import os
import json
from base64 import b64decode, urlsafe_b64decode, urlsafe_b64encode
from secrets import token_bytes
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialCipher:
    _BUNDLE_PREFIX = "nexus-vault-v1:"
    @classmethod
    def from_environment(cls) -> CredentialCipher:
        encoded = os.environ.get("NEXUS_ENCRYPTION_KEY") or os.environ["NEXUS_CREDENTIAL_ENCRYPTION_KEY_BASE64"]
        return cls(b64decode(encoded, validate=True))

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Credential encryption key must be 32 bytes")
        self._cipher = AESGCM(key)

    @staticmethod
    def _context(tenant_id: UUID, workspace_id: UUID, provider: str) -> bytes:
        return b"nexus-credential-v1\0" + tenant_id.bytes + workspace_id.bytes + provider.encode("utf-8")

    def encrypt(self, secret: str, tenant_id: UUID, workspace_id: UUID, provider: str) -> str:
        if not secret:
            raise ValueError("Credential cannot be empty")
        nonce = token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, secret.encode("utf-8"), self._context(tenant_id, workspace_id, provider))
        return urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, value: str, tenant_id: UUID, workspace_id: UUID, provider: str) -> str:
        data = urlsafe_b64decode(value.encode("ascii"))
        if len(data) < 29:
            raise ValueError("Invalid encrypted credential")
        plain = self._cipher.decrypt(data[:12], data[12:], self._context(tenant_id, workspace_id, provider))
        return plain.decode("utf-8")

    @classmethod
    def encode_fields(cls, fields: dict[str, str]) -> str:
        if not fields or any(not key or not value for key, value in fields.items()):
            raise ValueError("Credential fields cannot be empty")
        return cls._BUNDLE_PREFIX + json.dumps(fields, separators=(",", ":"), sort_keys=True)

    @classmethod
    def decode_fields(cls, value: str) -> dict[str, str]:
        if not value.startswith(cls._BUNDLE_PREFIX):
            return {"api_key": value}
        parsed = json.loads(value[len(cls._BUNDLE_PREFIX):])
        if not isinstance(parsed, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in parsed.items()):
            raise ValueError("Invalid encrypted credential bundle")
        return parsed
