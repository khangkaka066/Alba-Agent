"""Atomic budget and encrypted credential storage for the model gateway."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from nexus_model_gateway import BudgetExceeded, CredentialCipher, UsageRecord
from nexus_model_gateway.router import METERED, Provider, ResolvedCredential
from nexus_model_gateway.subscription_connectors import OPENAI_WIRE_PRESETS, ConnectorError, CopilotTokenBroker, credential_headers

from .entities import ModelCredential, Tenant, TenantBudget, TokenUsageLog
from .scope import scoped_session
from app.billing.plans import limits_for_plan



_DEFAULT_GATEWAY_HOST = "api.shopaikey.com"
# One endpoint serves every model family, so a default credential of these presets answers for any provider.
SERVES_ALL_PROVIDERS = frozenset({"shopaikey"}) | OPENAI_WIRE_PRESETS
COPILOT_BROKER = CopilotTokenBroker()


def _gateway_endpoint(base_url: str | None, provider: str) -> str:
    """Resolve the URL the user entered for the custom gateway; fall back to the built-in host."""
    root = (base_url or f"https://{_DEFAULT_GATEWAY_HOST}/v1").rstrip("/")
    return root if provider == "openai" else root.removesuffix("/v1")


class SqlGatewayStore:
    def __init__(self, engine: AsyncEngine, cipher: CredentialCipher, copilot: CopilotTokenBroker = COPILOT_BROKER) -> None:
        self._engine = engine
        self._cipher = cipher
        self._copilot = copilot

    async def _materialize(self, credential: ModelCredential, tenant_id: UUID, workspace_id: UUID, provider: Provider) -> ResolvedCredential:
        fields = CredentialCipher.decode_fields(self._cipher.decrypt(credential.encrypted_key, tenant_id, workspace_id, credential.provider))
        preset = credential.preset_id or ""
        if preset == "github_copilot":
            if not fields.get("oauth_token"):
                raise ConnectorError("The stored GitHub Copilot login is incomplete; sign in again")
            return await self._copilot.credential(fields["oauth_token"])
        settings = {key: str(value) for key, value in (credential.settings or {}).items()}
        api_key = fields.get("api_key", "")
        endpoint = _gateway_endpoint(credential.base_url, provider) if preset == "shopaikey" else credential.base_url
        return ResolvedCredential(
            api_key, endpoint, settings.get("billing_mode", METERED), credential_headers(preset, settings, api_key),
            "openai" if preset in OPENAI_WIRE_PRESETS else "native",
        )

    async def reserve(self, tenant_id: UUID, workspace_id: UUID, amount: Decimal) -> None:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
            if tenant is None:
                raise BudgetExceeded("Tenant is unavailable")
            limit = limits_for_plan(tenant.plan).max_monthly_cost_usd
            if limit is not None:
                now = datetime.now(timezone.utc)
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                spent = await session.scalar(
                    select(func.coalesce(func.sum(TokenUsageLog.total_cost_usd), Decimal("0"))).where(
                        TokenUsageLog.tenant_id == tenant_id,
                        TokenUsageLog.created_at >= month_start,
                        TokenUsageLog.managed_charge.is_(True),
                    )
                )
                budget = await session.get(TenantBudget, tenant_id)
                reserved = budget.reserved_usd if budget is not None else Decimal("0")
                if Decimal(str(spent or 0)) + reserved + amount > limit:
                    raise BudgetExceeded("Tenant monthly managed model spend limit reached")
            result = await session.execute(
                update(TenantBudget)
                .where(TenantBudget.tenant_id == tenant_id, TenantBudget.remaining_usd >= amount, TenantBudget.overage_usd == 0)
                .values(
                    remaining_usd=TenantBudget.remaining_usd - amount,
                    reserved_usd=TenantBudget.reserved_usd + amount,
                )
                .returning(TenantBudget.tenant_id)
            )
            if result.scalar_one_or_none() is None:
                raise BudgetExceeded("Tenant budget is insufficient")

    async def finalize(self, reserved: Decimal, usage: UsageRecord, charge_budget: bool) -> None:
        async with scoped_session(self._engine, usage.tenant_id, usage.workspace_id) as session:
            if charge_budget:
                result = await session.execute(
                    update(TenantBudget)
                    .where(
                        TenantBudget.tenant_id == usage.tenant_id,
                        TenantBudget.reserved_usd >= reserved,
                    )
                    .values(
                        remaining_usd=func.greatest(
                            Decimal("0"), TenantBudget.remaining_usd + reserved - usage.total_cost_usd
                        ),
                        reserved_usd=TenantBudget.reserved_usd - reserved,
                        overage_usd=TenantBudget.overage_usd + func.greatest(
                            Decimal("0"), usage.total_cost_usd - TenantBudget.remaining_usd - reserved
                        ),
                    )
                    .returning(TenantBudget.tenant_id)
                )
                if result.scalar_one_or_none() is None:
                    raise ValueError("Budget reservation was not found")
            session.add(
                TokenUsageLog(
                    tenant_id=usage.tenant_id,
                    workspace_id=usage.workspace_id,
                    workflow_id=usage.workflow_id,
                    run_id=usage.run_id,
                    agent_name=usage.agent_name,
                    provider=usage.provider,
                    model=usage.model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_cost_usd=usage.total_cost_usd,
                    sandbox_compute_seconds=usage.sandbox_compute_seconds,
                    latency_ms=usage.latency_ms,
                    managed_charge=charge_budget,
                    billing_mode=usage.billing_mode,
                )
            )

    async def release(self, tenant_id: UUID, workspace_id: UUID, amount: Decimal) -> None:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            result = await session.execute(
                update(TenantBudget)
                .where(TenantBudget.tenant_id == tenant_id, TenantBudget.reserved_usd >= amount)
                .values(
                    remaining_usd=TenantBudget.remaining_usd + amount,
                    reserved_usd=TenantBudget.reserved_usd - amount,
                )
                .returning(TenantBudget.tenant_id)
            )
            if result.scalar_one_or_none() is None:
                raise ValueError("Budget reservation was not found")

    async def get_credential(
        self, tenant_id: UUID, workspace_id: UUID, credential_id: UUID, provider: Provider
    ) -> str:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            credential = await session.scalar(
                select(ModelCredential).where(
                    ModelCredential.id == credential_id,
                    ModelCredential.tenant_id == tenant_id,
                    ModelCredential.workspace_id == workspace_id,
                    ModelCredential.provider == provider,
                )
            )
            if credential is None:
                raise LookupError("Credential not found in this workspace")
            return CredentialCipher.decode_fields(
                self._cipher.decrypt(credential.encrypted_key, tenant_id, workspace_id, provider)
            ).get("api_key", "")

    async def resolve_default_credential(
        self, tenant_id: UUID, workspace_id: UUID, provider: Provider
    ) -> ResolvedCredential | None:
        """Resolve an active workspace credential without moving secrets into process env."""
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            credential = await session.scalar(
                select(ModelCredential).where(
                    ModelCredential.tenant_id == tenant_id,
                    ModelCredential.workspace_id == workspace_id,
                    or_(ModelCredential.provider == provider, ModelCredential.preset_id.in_(SERVES_ALL_PROVIDERS)),
                    ModelCredential.status == "connected",
                    ModelCredential.is_default.is_(True),
                ).order_by(case((ModelCredential.provider == provider, 0), else_=1), ModelCredential.created_at.desc()).limit(1)
            )
            if credential is None:
                return None
            return await self._materialize(credential, tenant_id, workspace_id, provider)

    async def resolve_credential(
        self, tenant_id: UUID, workspace_id: UUID, credential_id: UUID, provider: Provider
    ) -> ResolvedCredential:
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            credential = await session.scalar(select(ModelCredential).where(
                ModelCredential.id == credential_id,
                ModelCredential.tenant_id == tenant_id,
                ModelCredential.workspace_id == workspace_id,
            ))
            if credential is None:
                raise LookupError("Credential not found in this workspace")
            if credential.provider != provider and credential.preset_id not in SERVES_ALL_PROVIDERS:
                raise LookupError("Credential does not support this provider")
            return await self._materialize(credential, tenant_id, workspace_id, provider)

    async def get_default_credential(
        self, tenant_id: UUID, workspace_id: UUID, provider: Provider
    ) -> tuple[str, str | None] | None:
        resolved = await self.resolve_default_credential(tenant_id, workspace_id, provider)
        return None if resolved is None else (resolved.api_key, resolved.api_base)

    async def get_credential_details(
        self, tenant_id: UUID, workspace_id: UUID, credential_id: UUID, provider: Provider
    ) -> tuple[str, str | None]:
        resolved = await self.resolve_credential(tenant_id, workspace_id, credential_id, provider)
        return resolved.api_key, resolved.api_base

    async def save_credential(
        self, tenant_id: UUID, workspace_id: UUID, provider: Provider, name: str, secret: str
    ) -> UUID:
        ciphertext = self._cipher.encrypt(secret, tenant_id, workspace_id, provider)
        row = ModelCredential(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            provider=provider,
            name=name,
            encrypted_key=ciphertext,
            key_version=1,
        )
        async with scoped_session(self._engine, tenant_id, workspace_id) as session:
            session.add(row)
            await session.flush()
            return row.id
