"""Workspace-scoped login and opaque service-key administration."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import os
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth.api_keys import issue_service_key
from app.auth.local import ensure_local_workspace, local_mode_enabled
from app.auth.context import Role, TenantContext, hash_password, issue_access_token, require_role, verify_password
from app.models import ServiceApiKey, Tenant, TenantBudget, User, Workspace, WorkspaceMember
from app.models.scope import scoped_session
from app.routers.common import get_services

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    workspace_id: UUID
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 900


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_name: str = Field(min_length=1, max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=1024)


class RegistrationRequest(SignupRequest):
    setup_token: str = Field(min_length=16, max_length=512)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=1024)


class SignupOptions(BaseModel):
    public_signup_enabled: bool


class RegistrationResponse(TokenResponse):
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID


class ServiceKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scopes: frozenset[Literal["read", "write", "run", "approve", "admin"]] = frozenset({"read"})


class ServiceKeyResponse(BaseModel):
    id: UUID
    key: str
    prefix: str
    scopes: frozenset[str]


def _public_signup_enabled() -> bool:
    return os.environ.get("NEXUS_PUBLIC_SIGNUP_ENABLED", "true").lower() == "true"


async def _limit_auth_request(request: Request, action: str, email: str, limit: int) -> None:
    pepper = os.environ["NEXUS_API_KEY_PEPPER"]
    digest = hmac.new(pepper.encode(), email.encode(), hashlib.sha256).hexdigest()
    redis = get_services(request).redis
    key = f"nexus:auth:{action}:{digest}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later")
    if action == "signup":
        global_key = "nexus:auth:signup:global"
        global_count = await redis.incr(global_key)
        if global_count == 1:
            await redis.expire(global_key, 3600)
        if global_count > 100:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Signup is temporarily busy. Try again later")


async def _create_workspace(body: SignupRequest, database_url: str, *, first_only: bool,
                            initial_credit: Decimal) -> RegistrationResponse:
    tenant_id, workspace_id, user_id = uuid4(), uuid4(), uuid4()
    email = body.email.strip().lower()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                await session.execute(text("SELECT pg_advisory_xact_lock(741926381)"))
                if first_only and await session.scalar(select(func.count()).select_from(Tenant)):
                    raise HTTPException(status.HTTP_409_CONFLICT, "Initial workspace is already registered")
                if not first_only and await session.scalar(select(User.id).where(User.email == email).limit(1)):
                    raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
                session.add(Tenant(id=tenant_id, name=body.tenant_name))
                await session.flush()
                session.add(Workspace(id=workspace_id, tenant_id=tenant_id, name=body.workspace_name))
                await session.flush()
                session.add(User(
                    id=user_id, tenant_id=tenant_id, workspace_id=workspace_id,
                    email=email, password_hash=hash_password(body.password),
                    display_name=body.display_name,
                ))
                session.add(WorkspaceMember(
                    tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id, role="owner",
                ))
                session.add(TenantBudget(
                    tenant_id=tenant_id,
                    remaining_usd=initial_credit,
                    reserved_usd=Decimal("0"), overage_usd=Decimal("0"),
                ))
    finally:
        await engine.dispose()
    token = issue_access_token(TenantContext(tenant_id, workspace_id, user_id, "owner"))
    return RegistrationResponse(access_token=token, tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id)


class LocalMode(BaseModel):
    enabled: bool


@router.get("/local-mode", response_model=LocalMode)
async def local_mode() -> LocalMode:
    return LocalMode(enabled=local_mode_enabled())


@router.post("/local-session", response_model=RegistrationResponse)
async def local_session() -> RegistrationResponse:
    """Session for the built-in local owner. Only exists when the server was started in local mode."""
    database_url = os.environ.get("NEXUS_SETUP_DATABASE_URL", "")
    if not local_mode_enabled() or not database_url:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Local mode is not enabled on this server")
    context = await ensure_local_workspace(database_url)
    return RegistrationResponse(access_token=issue_access_token(context), tenant_id=context.tenant_id,
                                workspace_id=context.workspace_id, user_id=context.user_id)


@router.get("/signup-options", response_model=SignupOptions)
async def signup_options() -> SignupOptions:
    return SignupOptions(public_signup_enabled=_public_signup_enabled())


@router.post("/signup", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, request: Request) -> RegistrationResponse:
    database_url = os.environ.get("NEXUS_SETUP_DATABASE_URL", "")
    if not _public_signup_enabled() or not database_url:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Public signup is unavailable")
    await _limit_auth_request(request, "signup", body.email.strip().lower(), 3)
    return await _create_workspace(body, database_url, first_only=False, initial_credit=Decimal("0"))


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegistrationRequest) -> RegistrationResponse:
    configured = os.environ.get("NEXUS_REGISTRATION_TOKEN", "")
    database_url = os.environ.get("NEXUS_SETUP_DATABASE_URL", "")
    if not configured or not database_url or not hmac.compare_digest(configured, body.setup_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "First workspace registration is unavailable")
    return await _create_workspace(
        body, database_url, first_only=True,
        initial_credit=Decimal(os.environ.get("NEXUS_NEW_TENANT_CREDIT_USD", "10")),
    )


@router.post("/login", response_model=RegistrationResponse)
async def login(body: LoginRequest, request: Request) -> RegistrationResponse:
    database_url = os.environ.get("NEXUS_SETUP_DATABASE_URL", "")
    if not database_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Account login is unavailable")
    email = body.email.strip().lower()
    await _limit_auth_request(request, "login", email, 10)
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as session:
            users = (await session.scalars(select(User).where(User.email == email).limit(3))).all()
            matches = [user for user in users if verify_password(body.password, user.password_hash)]
            if len(matches) != 1:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is invalid")
            user = matches[0]
            member = await session.scalar(select(WorkspaceMember).where(
                WorkspaceMember.tenant_id == user.tenant_id,
                WorkspaceMember.workspace_id == user.workspace_id,
                WorkspaceMember.user_id == user.id,
            ))
            if member is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Workspace membership is unavailable")
            context = TenantContext(user.tenant_id, user.workspace_id, user.id, cast(Role, member.role))
    finally:
        await engine.dispose()
    return RegistrationResponse(
        access_token=issue_access_token(context), tenant_id=context.tenant_id,
        workspace_id=context.workspace_id, user_id=context.user_id,
    )


@router.post("/token", response_model=TokenResponse)
async def create_token(body: TokenRequest, request: Request) -> TokenResponse:
    engine = get_services(request).engine
    async with scoped_session(engine, body.tenant_id, body.workspace_id) as session:
        user = await session.scalar(select(User).where(User.email == body.email))
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is invalid")
        member = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
        if member is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Workspace membership is unavailable")
        context = TenantContext(body.tenant_id, body.workspace_id, user.id, cast(Role, member.role))
    return TokenResponse(access_token=issue_access_token(context))


@router.post("/keys", response_model=ServiceKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_service_key(
    body: ServiceKeyRequest,
    request: Request,
    context: Annotated[TenantContext, Depends(require_role("admin", "admin"))],
) -> ServiceKeyResponse:
    if not body.scopes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one key scope is required")
    plain, prefix, key_hash = issue_service_key()
    identifier = uuid4()
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        session.add(ServiceApiKey(
            id=identifier, tenant_id=context.tenant_id, workspace_id=context.workspace_id,
            key_prefix=prefix, key_hash=key_hash, created_by_user_id=context.user_id,
            scopes=sorted(body.scopes),
        ))
    return ServiceKeyResponse(id=identifier, key=plain, prefix=prefix, scopes=body.scopes)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_service_key(
    key_id: UUID,
    request: Request,
    context: Annotated[TenantContext, Depends(require_role("admin", "admin"))],
) -> Response:
    async with scoped_session(get_services(request).engine, context.tenant_id, context.workspace_id) as session:
        row = await session.scalar(select(ServiceApiKey).where(ServiceApiKey.id == key_id).with_for_update())
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Service key is not visible in this workspace")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
