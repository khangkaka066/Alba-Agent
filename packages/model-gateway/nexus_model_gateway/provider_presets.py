"""Built-in, brand-neutral provider setup catalog and conservative price defaults."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Literal

Category = Literal["subscription", "unified", "direct", "local", "media", "tools", "channel"]


@dataclass(frozen=True)
class AuthFieldSpec:
    name: str
    label: str
    required: bool = True
    secret: bool = True
    placeholder: str = ""


@dataclass(frozen=True)
class ProviderModelSpec:
    id: str
    kind: Literal["chat", "embedding", "voice", "image", "video", "search"]
    prompt_usd_per_million: str | None = None
    completion_usd_per_million: str | None = None


@dataclass(frozen=True)
class ProviderPresetSpec:
    id: str
    name: str
    category: Category
    description: str
    protocol: str
    auth_fields: tuple[AuthFieldSpec, ...]
    base_url: str | None = None
    anthropic_base_url: str | None = None
    google_base_url: str | None = None
    balance_url_template: str | None = None
    models: tuple[ProviderModelSpec, ...] = ()
    icon: str = "✦"
    local: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _key(name: str = "api_key", placeholder: str = "") -> AuthFieldSpec:
    return AuthFieldSpec(name, "API key", placeholder=placeholder)


PRESETS: tuple[ProviderPresetSpec, ...] = (
    ProviderPresetSpec("openai_subscription", "ChatGPT Plus / Pro / Team", "subscription", "Run OpenAI models on your ChatGPT plan through Codex CLI credentials or a subscription bridge.", "openai-compatible", (), None, models=(ProviderModelSpec("gpt-5.4", "chat"), ProviderModelSpec("gpt-4.1-mini", "chat"), ProviderModelSpec("o3-mini", "chat")), icon="◉"),
    ProviderPresetSpec("claude_subscription", "Claude Pro / Max", "subscription", "Run Claude models on your Claude plan with a Claude Code token or a subscription bridge.", "anthropic", (), "https://api.anthropic.com", models=(ProviderModelSpec("claude-sonnet-4-6", "chat"), ProviderModelSpec("claude-opus-4-6", "chat")), icon="A"),
    ProviderPresetSpec("github_copilot", "GitHub Copilot", "subscription", "Sign in with a GitHub device code and use GPT, Claude and Gemini models included in your Copilot plan.", "openai-compatible", (), "https://api.githubcopilot.com", models=(ProviderModelSpec("gpt-4.1", "chat"), ProviderModelSpec("gpt-4o", "chat"), ProviderModelSpec("claude-sonnet-4", "chat"), ProviderModelSpec("gemini-2.5-pro", "chat")), icon="⌥"),
    ProviderPresetSpec("gemini_subscription", "Gemini Advanced / Code Assist", "subscription", "Use Gemini models with Gemini CLI Google-account credentials or a Google API bridge.", "gemini", (), "https://generativelanguage.googleapis.com", models=(ProviderModelSpec("gemini-2.5-pro", "chat"), ProviderModelSpec("gemini-2.5-flash", "chat")), icon="✳"),
    ProviderPresetSpec("shopaikey", "Nexus Harness", "unified", "Third-party API-key provider: connect any OpenAI-compatible endpoint by entering its URL and key, and optionally list the model IDs it serves.", "openai-compatible", (AuthFieldSpec("base_url", "API URL", True, False, "https://api.example.com/v1"), _key(placeholder="sk-…"), AuthFieldSpec("custom_model_ids", "Model IDs · comma separated, optional", False, False, "gpt-4.1-mini, claude-sonnet-4-6")), "https://api.shopaikey.com/v1", "https://api.shopaikey.com", "https://api.shopaikey.com", "https://api.shopaikey.com/usage?apiKey={api_key}", (
        ProviderModelSpec("gpt-4.1-mini", "chat", "0.40", "1.60"),
        ProviderModelSpec("gpt-5.4", "chat"), ProviderModelSpec("gpt-5.4-nano", "chat"),
        ProviderModelSpec("o3-mini-high", "chat"), ProviderModelSpec("claude-sonnet-4-6", "chat"),
        ProviderModelSpec("claude-opus-4-6", "chat"), ProviderModelSpec("gemini-2.5-flash", "chat"),
        ProviderModelSpec("gemini-2.5-pro", "chat"), ProviderModelSpec("deepseek-v3-1", "chat"),
        ProviderModelSpec("qwen3-coder-flash", "chat"),
        ProviderModelSpec("text-embedding-3-small", "embedding", "0.02", "0"),
        ProviderModelSpec("text-embedding-3-large", "embedding", "0.16", "0"),
        ProviderModelSpec("tts-1-hd", "voice"), ProviderModelSpec("speech-02-turbo", "voice"),
        ProviderModelSpec("gpt-image-2-all", "image"), ProviderModelSpec("veo-3.1", "video"),
    ), "◈"),
    ProviderPresetSpec("cliproxyapi", "CLIProxyAPI / local subscription bridge", "local", "A subscription bridge running on this machine that exposes your ChatGPT, Claude or Gemini plan as an OpenAI-compatible endpoint.", "openai-compatible", (AuthFieldSpec("api_key", "Bridge API key", False),), "http://host.docker.internal:8317/v1", models=(), icon="⇄", local=True),
    ProviderPresetSpec("openrouter", "OpenRouter", "unified", "Route to supported hosted models through one compatible endpoint.", "openai-compatible", (_key(),), "https://openrouter.ai/api/v1", models=(ProviderModelSpec("openai/gpt-4.1-mini", "chat"),), icon="↗"),
    ProviderPresetSpec("custom_openai_gateway", "Custom OpenAI-Compatible Gateway", "unified", "Connect a compatible hosted or private gateway.", "openai-compatible", (AuthFieldSpec("provider_name", "Provider name", False, False), AuthFieldSpec("base_url", "Base URL", True, False, "https://gateway.example/v1"), _key(), AuthFieldSpec("custom_model_ids", "Model IDs", False, False)), models=(), icon="⌘"),
    ProviderPresetSpec("openai", "OpenAI", "direct", "Official OpenAI API endpoint.", "openai-compatible", (_key(),), "https://api.openai.com/v1", models=(ProviderModelSpec("gpt-4.1-mini", "chat", "0.40", "1.60"), ProviderModelSpec("gpt-4o", "chat"), ProviderModelSpec("o3-mini", "chat"), ProviderModelSpec("text-embedding-3-small", "embedding", "0.02", "0"), ProviderModelSpec("text-embedding-3-large", "embedding", "0.16", "0"), ProviderModelSpec("whisper-1", "voice"), ProviderModelSpec("tts-1-hd", "voice")), icon="◉"),
    ProviderPresetSpec("anthropic", "Anthropic", "direct", "Official Anthropic Messages API.", "anthropic", (_key(),), "https://api.anthropic.com", models=(ProviderModelSpec("claude-sonnet-4-6", "chat"), ProviderModelSpec("claude-opus-4-6", "chat"), ProviderModelSpec("claude-3-5-haiku-latest", "chat")), icon="A"),
    ProviderPresetSpec("google_gemini", "Google Gemini", "direct", "Google GenAI API endpoint.", "gemini", (_key(),), "https://generativelanguage.googleapis.com", models=(ProviderModelSpec("gemini-2.5-flash", "chat"), ProviderModelSpec("gemini-2.5-pro", "chat"), ProviderModelSpec("text-embedding-004", "embedding")), icon="✳"),
    ProviderPresetSpec("deepseek", "DeepSeek", "direct", "Official DeepSeek compatible endpoint.", "openai-compatible", (_key(),), "https://api.deepseek.com/v1", models=(ProviderModelSpec("deepseek-chat", "chat"), ProviderModelSpec("deepseek-reasoner", "chat")), icon="◌"),
    ProviderPresetSpec("groq", "Groq", "direct", "Low-latency compatible inference.", "openai-compatible", (_key(),), "https://api.groq.com/openai/v1", models=(ProviderModelSpec("llama-3.3-70b-versatile", "chat"),), icon="ϟ"),
    ProviderPresetSpec("mistral", "Mistral", "direct", "Official Mistral API.", "openai-compatible", (_key(),), "https://api.mistral.ai/v1", models=(ProviderModelSpec("mistral-small-latest", "chat"),), icon="M"),
    ProviderPresetSpec("together_ai", "Together AI", "direct", "Hosted open model inference.", "openai-compatible", (_key(),), "https://api.together.xyz/v1", models=(ProviderModelSpec("meta-llama/Llama-3.3-70B-Instruct-Turbo", "chat"),), icon="T"),
    ProviderPresetSpec("ollama", "Ollama", "local", "Local models served by Ollama; no hosted API key required.", "openai-compatible", (), "http://host.docker.internal:11434/v1", models=(), icon="⌂", local=True),
    ProviderPresetSpec("lm_studio", "LM Studio", "local", "Local OpenAI-compatible model server.", "openai-compatible", (), "http://host.docker.internal:1234/v1", models=(), icon="⌂", local=True),
    ProviderPresetSpec("local_vllm", "vLLM", "local", "Self-hosted vLLM endpoint.", "openai-compatible", (), "http://host.docker.internal:8000/v1", models=(), icon="⌂", local=True),
    ProviderPresetSpec("elevenlabs", "ElevenLabs", "media", "Voice synthesis and speech services.", "http", (_key(), AuthFieldSpec("default_voice_id", "Default voice ID", False, False)), "https://api.elevenlabs.io/v1", icon="♫"),
    ProviderPresetSpec("cartesia", "Cartesia", "media", "Low-latency speech generation.", "http", (_key(),), "https://api.cartesia.ai", icon="♫"),
    ProviderPresetSpec("fish_audio", "Fish Audio", "media", "Speech generation and voice services.", "http", (_key(),), "https://api.fish.audio", icon="♫"),
    ProviderPresetSpec("minimax_tts", "MiniMax TTS", "media", "Text-to-speech services.", "http", (_key(),), "https://api.minimax.io", icon="♫"),
    ProviderPresetSpec("serper", "Serper Search", "tools", "Web search API for agent tools.", "http", (AuthFieldSpec("SERPER_API_KEY", "Serper API key"),), "https://google.serper.dev", icon="⌕"),
    ProviderPresetSpec("tavily", "Tavily", "tools", "Search API for research workflows.", "http", (AuthFieldSpec("TAVILY_API_KEY", "Tavily API key"),), "https://api.tavily.com", icon="⌕"),
    ProviderPresetSpec("firecrawl", "Firecrawl", "tools", "Web extraction and crawling API.", "http", (AuthFieldSpec("FIRECRAWL_API_KEY", "Firecrawl API key"),), "https://api.firecrawl.dev/v2", icon="⌕"),
    ProviderPresetSpec("composio", "Composio", "tools", "Managed application integrations.", "http", (AuthFieldSpec("COMPOSIO_API_KEY", "Composio API key"),), "https://backend.composio.dev/api/v3.1", icon="⌘"),
    ProviderPresetSpec("pipedream", "Pipedream", "tools", "Managed application integrations.", "http", (AuthFieldSpec("PIPEDREAM_CLIENT_ID", "Client ID"), AuthFieldSpec("PIPEDREAM_CLIENT_SECRET", "Client secret"), AuthFieldSpec("PIPEDREAM_PROJECT_ID", "Project ID", True, False)), icon="⌘"),
    ProviderPresetSpec("tiktok", "TikTok", "channel", "Let your agent team publish videos to your TikTok account.", "http", (AuthFieldSpec("access_token", "Access token"),), "https://open.tiktokapis.com", icon="♪"),
    ProviderPresetSpec("facebook", "Facebook Page", "channel", "Let your agent team post to your Facebook Page.", "http", (AuthFieldSpec("access_token", "Page access token"), AuthFieldSpec("page_id", "Page ID", False, False)), "https://graph.facebook.com/v19.0", icon="f"),
    ProviderPresetSpec("youtube", "YouTube", "channel", "Let your agent team upload videos to your YouTube channel.", "http", (AuthFieldSpec("access_token", "OAuth access token"),), "https://www.googleapis.com/youtube/v3", icon="▶"),
    ProviderPresetSpec("e2b", "E2B Sandbox", "tools", "Cloud computer sandbox provider.", "http", (_key(), AuthFieldSpec("region", "Region", False, False), AuthFieldSpec("container_shape", "Container shape", False, False)), icon="▣"),
    ProviderPresetSpec("daytona", "Daytona Sandbox", "tools", "Cloud computer sandbox provider.", "http", (_key(), AuthFieldSpec("region", "Region", False, False), AuthFieldSpec("container_shape", "Container shape", False, False)), "https://app.daytona.io/api", icon="▣"),
    ProviderPresetSpec("createos", "CreateOS Sandbox", "tools", "Cloud computer sandbox provider.", "http", (_key(), AuthFieldSpec("region", "Region", False, False), AuthFieldSpec("container_shape", "Container shape", False, False)), icon="▣"),
    ProviderPresetSpec("boat", "Boat Sandbox", "tools", "Cloud computer sandbox provider.", "http", (_key(), AuthFieldSpec("region", "Region", False, False), AuthFieldSpec("container_shape", "Container shape", False, False)), icon="▣"),
    ProviderPresetSpec("railway", "Railway Sandbox", "tools", "Cloud computer sandbox provider.", "http", (_key(), AuthFieldSpec("region", "Region", False, False), AuthFieldSpec("container_shape", "Container shape", False, False)), "https://backboard.railway.com/graphql/v2", icon="▣"),
)

PRESETS_BY_ID = {preset.id: preset for preset in PRESETS}


def default_model_rates() -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """Return only prices explicitly maintained in the built-in registry."""
    rates: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for preset in PRESETS:
        provider = "openai" if preset.id == "shopaikey" else preset.id
        for model in preset.models:
            if model.prompt_usd_per_million is not None:
                rates[(provider, model.id)] = (
                    Decimal(model.prompt_usd_per_million),
                    Decimal(model.completion_usd_per_million or "0"),
                )
    return rates
