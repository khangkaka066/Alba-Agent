"""Monthly AI plan connectors: credential-file parsers, GitHub Copilot device login and session-token minting.

A subscription credential is billed by the plan rather than per token, so a stored credential carries
``billing_mode=SUBSCRIPTION_INCLUDED`` and the gateway records zero per-token cost for it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping

import httpx

from .router import SUBSCRIPTION_INCLUDED, ResolvedCredential

# Public OAuth application identifier used by editor extensions for the GitHub device login.
GITHUB_COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_SESSION_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_DEFAULT_API = "https://api.githubcopilot.com"
COPILOT_HEADERS: Mapping[str, str] = {
    "Editor-Version": "vscode/1.99.0",
    "Editor-Plugin-Version": "copilot-chat/0.26.0",
    "Copilot-Integration-Id": "vscode-chat",
    "User-Agent": "GitHubCopilotChat/0.26.0",
}
ANTHROPIC_OAUTH_BETA = "oauth-2025-04-20"

# Presets whose single endpoint speaks the OpenAI chat format for every model family.
OPENAI_WIRE_PRESETS = frozenset({"github_copilot", "cliproxyapi"})
SUBSCRIPTION_PRESETS = frozenset({"openai_subscription", "claude_subscription", "gemini_subscription", "github_copilot"})


class ConnectorError(ValueError):
    """The supplied subscription credential cannot be used; the message is safe to show to the user."""


@dataclass(frozen=True)
class ImportedSubscription:
    secrets: dict[str, str]
    settings: dict[str, str]
    expires_at: datetime | None = None


@dataclass(frozen=True)
class ConnectorSpec:
    id: str
    name: str
    vendor: str
    provider: str
    description: str
    plans: tuple[str, ...]
    auth_methods: tuple[str, ...]
    models: tuple[str, ...]
    credential_hint: str
    needs_base_url: bool = False
    base_url: str | None = None
    notice: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id, "name": self.name, "vendor": self.vendor, "provider": self.provider,
            "description": self.description, "plans": list(self.plans), "auth_methods": list(self.auth_methods),
            "models": list(self.models), "credential_hint": self.credential_hint,
            "needs_base_url": self.needs_base_url, "base_url": self.base_url, "notice": self.notice,
        }


CONNECTORS: tuple[ConnectorSpec, ...] = (
    ConnectorSpec(
        "openai_subscription", "OpenAI · ChatGPT Plus / Pro / Team", "openai", "openai",
        "Run GPT and o-series models on your ChatGPT plan through Codex CLI credentials or a subscription bridge.",
        ("Plus", "Pro", "Team"), ("mounted_file", "paste_json", "bridge_token"),
        ("gpt-5.4", "gpt-4.1-mini", "o3-mini"),
        "Codex CLI file ~/.codex/auth.json, or the token of your subscription bridge", needs_base_url=True,
        notice="A ChatGPT plan token is accepted only by endpoints that understand it. Enter the URL of your subscription bridge.",
    ),
    ConnectorSpec(
        "claude_subscription", "Anthropic · Claude Pro / Max", "anthropic", "anthropic",
        "Run Claude models on your Claude plan with a Claude Code OAuth token or a subscription bridge.",
        ("Pro", "Max"), ("mounted_file", "paste_token", "bridge_token"),
        ("claude-sonnet-4-6", "claude-opus-4-6"),
        "Output of `claude setup-token`, ~/.claude/.credentials.json, or the ANTHROPIC_AUTH_TOKEN of your bridge",
        base_url="https://api.anthropic.com",
        notice="Anthropic restricts plan OAuth tokens to its own apps. Use a bridge or a token you are permitted to use this way.",
    ),
    ConnectorSpec(
        "github_copilot", "GitHub Copilot", "github", "openai",
        "Sign in with the GitHub device code and use GPT, Claude and Gemini models included in your Copilot plan.",
        ("Individual", "Business", "Enterprise"), ("device_flow", "mounted_file"),
        ("gpt-4.1", "gpt-4o", "claude-sonnet-4", "gemini-2.5-pro"),
        "Sign in with a code, or mount ~/.config/github-copilot/apps.json", base_url=COPILOT_DEFAULT_API,
    ),
    ConnectorSpec(
        "gemini_subscription", "Google · Gemini Advanced / Code Assist", "google", "gemini",
        "Use Gemini models with Gemini CLI Google-account credentials or a Google API bridge.",
        ("Advanced", "Code Assist"), ("mounted_file", "paste_json", "bridge_token"),
        ("gemini-2.5-pro", "gemini-2.5-flash"),
        "Gemini CLI file ~/.gemini/oauth_creds.json, or the token of your Google API bridge", needs_base_url=True,
        base_url="https://generativelanguage.googleapis.com",
    ),
)
CONNECTORS_BY_ID = {item.id: item for item in CONNECTORS}


def _jwt_claims(token: str) -> dict[str, Any]:
    """Read the unverified payload of a JWT; used only to show plan and expiry, never to trust it."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _expiry_from_exp(claims: Mapping[str, Any]) -> datetime | None:
    exp = claims.get("exp")
    return datetime.fromtimestamp(float(exp), timezone.utc) if isinstance(exp, (int, float)) else None


def _load_json(text: str, what: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConnectorError(f"{what} is not valid JSON") from error
    if not isinstance(data, dict):
        raise ConnectorError(f"{what} must be a JSON object")
    return data


def _ensure_unexpired(expires_at: datetime | None, what: str) -> None:
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise ConnectorError(f"{what} has expired; sign in again with the vendor CLI and re-import it")


def parse_codex_auth(text: str) -> ImportedSubscription:
    """Codex CLI ``auth.json``: either a ChatGPT-plan OAuth session or a plain API key."""
    stripped = text.strip()
    if stripped and not stripped.startswith("{"):
        if any(character.isspace() for character in stripped):
            raise ConnectorError("Paste the Codex auth.json file or a single bridge token")
        return ImportedSubscription({"api_key": stripped}, {"auth_kind": "api_key", "plan": "bridge"})
    data = _load_json(text, "Codex auth file")
    tokens = data.get("tokens")
    access = tokens.get("access_token") if isinstance(tokens, dict) else None
    if isinstance(access, str) and access:
        claims = _jwt_claims(access)
        expires_at = _expiry_from_exp(claims)
        _ensure_unexpired(expires_at, "The ChatGPT session")
        auth_claims = claims.get("https://api.openai.com/auth")
        auth_claims = auth_claims if isinstance(auth_claims, dict) else {}
        account = str((tokens or {}).get("account_id") or auth_claims.get("chatgpt_account_id") or "")
        settings = {"auth_kind": "oauth_token", "plan": str(auth_claims.get("chatgpt_plan_type") or "chatgpt")}
        if account:
            settings["account_id"] = account
        return ImportedSubscription({"api_key": access}, settings, expires_at)
    key = data.get("OPENAI_API_KEY")
    if isinstance(key, str) and key:
        return ImportedSubscription({"api_key": key}, {"auth_kind": "api_key", "plan": "api-key"})
    raise ConnectorError("The Codex auth file has neither a ChatGPT session nor an API key; run `codex login` first")


def parse_claude_credentials(text: str) -> ImportedSubscription:
    """Claude Code ``.credentials.json`` or a bare ``sk-ant-oat…`` token from `claude setup-token`."""
    stripped = text.strip()
    if stripped and not stripped.startswith("{"):
        if not stripped.startswith("sk-ant-") or any(character.isspace() for character in stripped):
            raise ConnectorError("Paste a Claude Code OAuth token (starts with sk-ant-) or the .credentials.json file")
        return ImportedSubscription({"api_key": stripped}, {"auth_kind": "oauth_token", "plan": "claude"})
    data = _load_json(text, "Claude credentials file")
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict) or not isinstance(oauth.get("accessToken"), str) or not oauth["accessToken"]:
        raise ConnectorError("The Claude credentials file has no OAuth session; run `claude login` first")
    expires_ms = oauth.get("expiresAt")
    expires_at = datetime.fromtimestamp(float(expires_ms) / 1000, timezone.utc) if isinstance(expires_ms, (int, float)) else None
    _ensure_unexpired(expires_at, "The Claude session")
    return ImportedSubscription(
        {"api_key": oauth["accessToken"]},
        {"auth_kind": "oauth_token", "plan": str(oauth.get("subscriptionType") or "claude")}, expires_at,
    )


def parse_gemini_credentials(text: str) -> ImportedSubscription:
    """Gemini CLI ``oauth_creds.json`` (Google account) or a bare API/bridge token."""
    stripped = text.strip()
    if stripped and not stripped.startswith("{"):
        if any(character.isspace() for character in stripped):
            raise ConnectorError("Paste the Gemini CLI oauth_creds.json file or a single token")
        return ImportedSubscription({"api_key": stripped}, {"auth_kind": "api_key", "plan": "gemini"})
    data = _load_json(text, "Gemini credentials file")
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise ConnectorError("The Gemini credentials file has no access token; run the Gemini CLI login first")
    expiry_ms = data.get("expiry_date")
    expires_at = datetime.fromtimestamp(float(expiry_ms) / 1000, timezone.utc) if isinstance(expiry_ms, (int, float)) else None
    _ensure_unexpired(expires_at, "The Google session")
    return ImportedSubscription({"api_key": access}, {"auth_kind": "oauth_token", "plan": "gemini-code-assist"}, expires_at)


def parse_copilot_apps(text: str) -> ImportedSubscription:
    """Editor-written ``apps.json`` / ``hosts.json``: the long-lived GitHub OAuth token for github.com."""
    data = _load_json(text, "GitHub Copilot credentials file")
    for name, entry in data.items():
        if name.startswith("github.com") and isinstance(entry, dict) and isinstance(entry.get("oauth_token"), str) and entry["oauth_token"]:
            return ImportedSubscription({"oauth_token": entry["oauth_token"]}, {"auth_kind": "device_flow", "plan": "copilot"})
    raise ConnectorError("No github.com Copilot login was found in this file; sign in with a device code instead")


PARSERS: dict[str, Callable[[str], ImportedSubscription]] = {
    "openai_subscription": parse_codex_auth,
    "claude_subscription": parse_claude_credentials,
    "gemini_subscription": parse_gemini_credentials,
    "github_copilot": parse_copilot_apps,
}

# Where each CLI keeps its login, relative to the read-only subscriptions mount.
MOUNTED_FILES: dict[str, tuple[str, ...]] = {
    "openai_subscription": ("codex/auth.json",),
    "claude_subscription": ("claude/.credentials.json",),
    "gemini_subscription": ("gemini/oauth_creds.json",),
    "github_copilot": ("github-copilot/apps.json", "github-copilot/hosts.json"),
}


def billing_for(preset_id: str, auth_kind: str, custom_base_url: bool) -> str:
    """Plan credentials and bridges are flat-rate; a bare vendor API key pasted into a plan connector is still metered."""
    from .router import METERED

    if preset_id in SUBSCRIPTION_PRESETS and auth_kind == "api_key" and not custom_base_url:
        return METERED
    return SUBSCRIPTION_INCLUDED if preset_id in SUBSCRIPTION_PRESETS or preset_id in OPENAI_WIRE_PRESETS else METERED


def credential_headers(preset_id: str, settings: Mapping[str, str], api_key: str) -> Mapping[str, str]:
    """Extra request headers a stored subscription credential needs, derived only from non-secret settings."""
    headers: dict[str, str] = {}
    if preset_id == "claude_subscription" and settings.get("auth_kind") == "oauth_token":
        headers.update({"Authorization": f"Bearer {api_key}", "anthropic-beta": ANTHROPIC_OAUTH_BETA})
    if preset_id == "openai_subscription" and settings.get("account_id"):
        headers["chatgpt-account-id"] = settings["account_id"]
    if preset_id == "gemini_subscription" and settings.get("auth_kind") == "oauth_token":
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


# --- GitHub Copilot device login -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class DevicePollResult:
    status: Literal["pending", "slow_down", "authorized", "expired", "denied"]
    oauth_token: str | None = None
    interval: int | None = None


HttpClientFactory = Callable[[], httpx.AsyncClient]


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=6.0), follow_redirects=False)


async def start_device_login(client_factory: HttpClientFactory = _default_client) -> DeviceCode:
    async with client_factory() as client:
        response = await client.post(
            GITHUB_DEVICE_CODE_URL, headers={"Accept": "application/json"},
            data={"client_id": GITHUB_COPILOT_CLIENT_ID, "scope": "read:user"},
        )
        response.raise_for_status()
        body = response.json()
    try:
        return DeviceCode(str(body["device_code"]), str(body["user_code"]), str(body["verification_uri"]),
                          int(body.get("expires_in", 900)), max(1, int(body.get("interval", 5))))
    except (KeyError, TypeError, ValueError) as error:
        raise ConnectorError("GitHub returned an unexpected device login response") from error


async def poll_device_login(device_code: str, client_factory: HttpClientFactory = _default_client) -> DevicePollResult:
    async with client_factory() as client:
        response = await client.post(
            GITHUB_TOKEN_URL, headers={"Accept": "application/json"},
            data={"client_id": GITHUB_COPILOT_CLIENT_ID, "device_code": device_code,
                  "grant_type": "urn:ietf:params:oauth:grant-type:device_code"},
        )
        response.raise_for_status()
        body = response.json()
    token = body.get("access_token")
    if isinstance(token, str) and token:
        return DevicePollResult("authorized", token)
    error = body.get("error")
    if error == "authorization_pending":
        return DevicePollResult("pending")
    if error == "slow_down":
        return DevicePollResult("slow_down", interval=int(body.get("interval", 10)))
    if error == "expired_token":
        return DevicePollResult("expired")
    if error == "access_denied":
        return DevicePollResult("denied")
    raise ConnectorError("GitHub rejected the device login")


@dataclass
class CopilotSession:
    token: str
    api_base: str
    expires_at: float


@dataclass
class CopilotTokenBroker:
    """Mints and caches the short-lived Copilot session token for a stored GitHub OAuth token."""

    client_factory: HttpClientFactory = _default_client
    clock: Callable[[], float] = time.time
    refresh_margin: float = 120.0
    _sessions: dict[str, CopilotSession] = field(default_factory=dict)

    async def session(self, oauth_token: str) -> CopilotSession:
        cache_key = hashlib.sha256(oauth_token.encode()).hexdigest()
        cached = self._sessions.get(cache_key)
        if cached is not None and cached.expires_at - self.refresh_margin > self.clock():
            return cached
        async with self.client_factory() as client:
            response = await client.get(
                COPILOT_SESSION_URL, headers={"Authorization": f"token {oauth_token}", "Accept": "application/json", **COPILOT_HEADERS},
            )
        if response.status_code in (401, 403, 404):
            raise ConnectorError("GitHub did not issue a Copilot session; check that this account has an active Copilot plan")
        response.raise_for_status()
        body = response.json()
        token = body.get("token")
        endpoints = body.get("endpoints")
        api = endpoints.get("api") if isinstance(endpoints, dict) else None
        if not isinstance(token, str) or not token:
            raise ConnectorError("GitHub returned no Copilot session token")
        expires = body.get("expires_at")
        fresh = CopilotSession(token, str(api or COPILOT_DEFAULT_API).rstrip("/"),
                               float(expires) if isinstance(expires, (int, float)) else self.clock() + 1500)
        self._sessions[cache_key] = fresh
        return fresh

    async def credential(self, oauth_token: str) -> ResolvedCredential:
        session = await self.session(oauth_token)
        return ResolvedCredential(session.token, session.api_base, SUBSCRIPTION_INCLUDED, dict(COPILOT_HEADERS), "openai")


async def list_copilot_models(broker: CopilotTokenBroker, oauth_token: str,
                              client_factory: HttpClientFactory = _default_client) -> list[str]:
    session = await broker.session(oauth_token)
    async with client_factory() as client:
        response = await client.get(f"{session.api_base}/models", headers={"Authorization": f"Bearer {session.token}", **COPILOT_HEADERS})
    response.raise_for_status()
    data = response.json().get("data", [])
    return sorted({str(item["id"]) for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)
                   and item.get("capabilities", {}).get("type", "chat") == "chat"})

