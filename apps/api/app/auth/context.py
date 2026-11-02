"""Signed access tokens, scoped service keys, and database-backed RBAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import ServiceApiKey, User, WorkspaceMember
from app.models.scope import scoped_session
from .api_keys import verify_service_key
from .api_keys import hash_service_key

Role = Literal["owner", "admin", "builder", "viewer"]
ROLE_RANK: dict[str, int] = {"viewer": 0, "builder": 1, "admin": 2, "owner": 3}
TOKEN_ISSUER = "nexus-agent-studio"
TOKEN_AUDIENCE = "nexus-api"


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    role: Role
    service_key: bool = False
    scopes: frozenset[str] = frozenset()


def _secret() -> bytes:
    value = os.environ.get("NEXUS_SECRET_KEY", "").encode()
    if len(value) < 32:
        raise RuntimeError("NEXUS_SECRET_KEY must contain at least 32 bytes")
    return value


def _segment(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def issue_access_token(context: TenantContext, ttl_seconds: int = 900) -> str:
    if not 60 <= ttl_seconds <= 86_400 or context.service_key:
        raise ValueError("Access token duration or issuer context is invalid")
    now = int(time.time())
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment({
        "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE,
        "sub": str(context.user_id), "tid": str(context.tenant_id),
        "wid": str(context.workspace_id), "iat": now, "nbf": now,
        "exp": now + ttl_seconds, "jti": secrets.token_hex(16),
    })
    signed = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(hmac.digest(_secret(), signed.encode(), "sha256")).rstrip(b"=").decode()
    return f"{signed}.{signature}"


def issue_voice_token(context: TenantContext, bot_id: UUID, ttl_seconds: int = 300) -> str:
    if not 60 <= ttl_seconds <= 600 or context.service_key:
        raise ValueError("Voice token duration or issuer context is invalid")
    now = int(time.time())
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment({
        "iss": TOKEN_ISSUER, "aud": "nexus-voice", "sub": str(context.user_id),
        "tid": str(context.tenant_id), "wid": str(context.workspace_id),
        "bid": str(bot_id), "scope": "voice", "iat": now, "nbf": now,
        "exp": now + ttl_seconds, "jti": secrets.token_hex(16),
    })
    signed = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(hmac.digest(_secret(), signed.encode(), "sha256")).rstrip(b"=").decode()
    return f"{signed}.{signature}"


def decode_access_token(token: str) -> tuple[UUID, UUID, UUID]:
    try:
        header, payload, signature = token.split(".")
        if len(token) > 4096 or not header or not payload or not signature:
            raise ValueError("Malformed token")
        signed = f"{header}.{payload}"
        expected = hmac.digest(_secret(), signed.encode(), "sha256")
        provided = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, provided):
            raise ValueError("Invalid signature")
        decoded_header = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        now = int(time.time())
        if decoded_header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("Unsupported token header")
        if claims.get("iss") != TOKEN_ISSUER or claims.get("aud") != TOKEN_AUDIENCE:
            raise ValueError("Invalid issuer or audience")
        if not all(isinstance(claims.get(key), int) for key in ("iat", "nbf", "exp")):
            raise ValueError("Missing token times")
        if claims["iat"] > now + 30 or claims["nbf"] > now or claims["exp"] <= now or claims["exp"] - claims["iat"] > 86_400:
            raise ValueError("Token is not currently valid")
        if not isinstance(claims.get("jti"), str) or len(claims["jti"]) < 16:
            raise ValueError("Token identifier is invalid")
        return UUID(claims["tid"]), UUID(claims["wid"]), UUID(claims["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Invalid access token") from error


def decode_voice_token(token: str, expected_bot_id: UUID) -> tuple[UUID, UUID, UUID]:
    try:
        header, payload, signature = token.split(".")
        if len(token) > 4096:
            raise ValueError("Malformed token")
        signed = f"{header}.{payload}"
        expected = hmac.digest(_secret(), signed.encode(), "sha256")
        provided = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        decoded_header = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        now = int(time.time())
        if not hmac.compare_digest(expected, provided) or decoded_header != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("Invalid signature")
        if claims.get("iss") != TOKEN_ISSUER or claims.get("aud") != "nexus-voice":
            raise ValueError("Invalid voice token audience")
        if claims.get("scope") != "voice" or UUID(claims["bid"]) != expected_bot_id:
            raise ValueError("Voice token scope does not match the requested bot")
        if not all(isinstance(claims.get(key), int) for key in ("iat", "nbf", "exp")):
            raise ValueError("Voice token times are missing")
        if claims["iat"] > now + 30 or claims["nbf"] > now or claims["exp"] <= now or claims["exp"] - claims["iat"] > 600:
            raise ValueError("Voice token is not currently valid")
        return UUID(claims["tid"]), UUID(claims["wid"]), UUID(claims["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Invalid voice token") from error


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Password length must be 12 to 1024 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(rounds) != 600_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


async def _membership(engine: AsyncEngine, tenant_id: UUID, workspace_id: UUID, user_id: UUID) -> Role:
    async with scoped_session(engine, tenant_id, workspace_id) as session:
        user = await session.get(User, user_id)
        member = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user_id))
        if user is None or member is None or member.role not in ROLE_RANK:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Workspace membership is unavailable")
        return member.role  # type: ignore[return-value]


async def tenant_context(request: Request) -> TenantContext:
    engine: AsyncEngine = request.app.state.services.engine
    authorization = request.headers.get("authorization", "")
    explicit_key = request.headers.get("x-nexus-api-key")
    token = explicit_key or (authorization[7:] if authorization.lower().startswith("bearer ") else "")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required")
    if token.startswith("nx-sk-"):
        try:
            tenant_id = UUID(request.headers["x-nexus-tenant-id"])
            workspace_id = UUID(request.headers["x-nexus-workspace-id"])
        except (KeyError, ValueError) as error:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Service key scope headers are required") from error
        async with scoped_session(engine, tenant_id, workspace_id) as session:
            key = await session.scalar(select(ServiceApiKey).where(
                ServiceApiKey.key_prefix == token[:18],
                ServiceApiKey.key_hash == hash_service_key(token, os.environ["NEXUS_API_KEY_PEPPER"].encode()),
            ))
            if key is None or key.revoked_at is not None or not verify_service_key(token, key.key_hash):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Service key is invalid")
            user_id = key.created_by_user_id
            scopes = frozenset(key.scopes)
        role = await _membership(engine, tenant_id, workspace_id, user_id)
        return TenantContext(tenant_id, workspace_id, user_id, role, True, scopes)
    try:
        tenant_id, workspace_id, user_id = decode_access_token(token)
    except ValueError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Access token is invalid") from error
    role = await _membership(engine, tenant_id, workspace_id, user_id)
    return TenantContext(tenant_id, workspace_id, user_id, role)


def require_role(minimum: Role, scope: str = "read") -> object:
    async def guard(context: TenantContext = Depends(tenant_context)) -> TenantContext:
        if ROLE_RANK[context.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Workspace role is insufficient")
        if context.service_key and scope not in context.scopes and "admin" not in context.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Service key scope is insufficient")
        return context

    return guard
