"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest, readError } from "@/lib/api";
import { SubscriptionHub } from "@/components/providers/subscription-hub";
import type { NavPage } from "@/components/studio-app";

type Model = { id: string; kind: string; prompt_usd_per_million: string | null; completion_usd_per_million: string | null };
type Preset = { id: string; name: string; category: string; description: string; protocol: string; base_url: string | null; models: Model[]; auth_fields: { name: string; label: string; required: boolean; secret: boolean; placeholder: string }[]; icon: string; local: boolean };
type Credential = { id: string; preset_id: string; provider: string; masked_key: string | null; status: string; base_url: string | null; is_default: boolean; available_models: string[]; default_models: Record<string, string>; settings: Record<string, string>; balance: Record<string, unknown> | null; safe_error: string | null };
type Category = "subscription" | "unified" | "direct" | "local" | "media" | "tools" | "channel";
const categoryNames: Record<Category, string> = { subscription: "Subscription plans", unified: "Unified gateways", direct: "Direct model providers", local: "Local models & subscription bridges", media: "Voice & media", tools: "Search, integrations & sandbox", channel: "Social channels" };
const marketplaceCategories: Category[] = ["unified", "direct", "local", "media", "tools"];
// The everyday "other models" row; everything else lives under expert mode.
const OTHER_MODEL_PRESETS = ["openai", "anthropic", "ollama"];
const modelRoles = [
  ["orchestrator", "Default orchestrator LLM", "chat"], ["fast", "Default fast / low-cost LLM", "chat"],
  ["coding", "Default coding sandbox LLM", "chat"], ["embedding", "Default embedding model", "embedding"], ["voice", "Default voice TTS / STT", "voice"],
] as const;

function modelReference(preset: Preset, model: Model): string {
  let provider = preset.id;
  if (preset.id === "shopaikey") {
    provider = model.id.startsWith("claude-") ? "anthropic" : model.id.startsWith("gemini-") || model.id.startsWith("text-embedding-004") ? "gemini" : model.id.startsWith("deepseek-") ? "deepseek" : "openai";
  } else if (preset.id === "openai_subscription") provider = "openai";
  else if (preset.id === "claude_subscription") provider = "anthropic";
  else if (preset.id === "gemini_subscription" || preset.id === "google_gemini") provider = "gemini";
  else if (preset.id === "github_copilot") provider = model.id.startsWith("claude-") ? "anthropic" : model.id.startsWith("gemini-") ? "gemini" : "openai";
  else if (preset.id === "cliproxyapi") provider = "openai";
  else if (preset.id === "lm_studio" || preset.id === "local_vllm") provider = "vllm";
  else if (preset.id === "custom_openai_gateway") provider = "openai";
  return `${provider}/${model.id}`;
}

/** Alba Harness: any third-party OpenAI-compatible provider, connected with its URL and API key. */
function HarnessCard({ token, saved, onChanged }: { token: string; saved?: Credential; onChanged: () => Promise<void> }) {
  const { t } = useLocale();
  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [models, setModels] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { if (saved) { setUrl(saved.base_url ?? ""); setModels(saved.settings.custom_model_ids ?? ""); } }, [saved]);
  const save = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      const credential = await apiRequest<Credential>("/api/v1/settings/credentials", token, { method: "POST", body: JSON.stringify({
        preset_id: "shopaikey", api_key: key, base_url: url.trim(), is_default: true, settings: models.trim() ? { custom_model_ids: models.trim() } : {},
      }) });
      const result = await apiRequest<{ status: string; available_models: string[]; suspect_models?: string[]; unlisted_models?: string[]; error: string | null }>(`/api/v1/settings/credentials/${credential.id}/test`, token, { method: "POST" });
      setKey("");
      const suspect = result.suspect_models ?? [], unlisted = result.unlisted_models ?? [];
      const warnings = (suspect.length ? t("harness.suspect", { count: suspect.length, names: suspect.slice(0, 4).join(", ") }) : "") + (unlisted.length ? t("harness.unlisted", { names: unlisted.slice(0, 4).join(", ") }) : "");
      setMessage(result.status === "CONNECTED" ? t("harness.savedVerified", { models: result.available_models.length ? t("harness.models", { count: result.available_models.length }) : "" }) + warnings : result.error ?? t("harness.unverified"));
      await onChanged();
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  const connected = saved?.status === "CONNECTED";
  return <div className="harness-card" data-provider="nexus-harness">
    <span className={`provider-status provider-status--${saved?.status.toLowerCase() ?? "unconfigured"}`}>{connected ? t("common.connected") : saved ? saved.status : t("common.notAdded")}</span>
    <label className="field"><span>{t("harness.url")}</span><input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://api.example.com/v1" spellCheck={false} /></label>
    <label className="field"><span>API Key</span><input type="password" autoComplete="off" value={key} onChange={(event) => setKey(event.target.value)} placeholder={saved?.masked_key ? t("harness.using", { key: saved.masked_key }) : "sk-…"} /></label>
    <label className="field harness-card__models"><span>{t("harness.modelsLabel")}</span><input value={models} onChange={(event) => setModels(event.target.value)} placeholder={t("harness.modelsPlaceholder")} spellCheck={false} /></label>
    <button className="button button-primary" disabled={busy || !key.trim() || !url.trim().startsWith("https://") || !token} onClick={() => void save()}>{busy ? t("common.checking") : t("common.saveCheck")}</button>
    {message && <p className="harness-card__note" role="status">{message}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}

export function ProviderSettings({ token, onNavigate }: { token: string; onNavigate: (page: NavPage) => void }) {
  const { t } = useLocale();
  const [expert, setExpert] = useState(false);
  useEffect(() => { try { setExpert(window.localStorage.getItem("nexus_expert_mode") === "1"); } catch { /* storage blocked: expert mode stays off */ } }, []);
  const changeExpert = (value: boolean) => { setExpert(value); try { window.localStorage.setItem("nexus_expert_mode", value ? "1" : "0"); } catch { /* keep the in-memory choice */ } };
  const [presets, setPresets] = useState<Preset[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<Preset | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [extraSecrets, setExtraSecrets] = useState<Record<string, string>>({});
  const [providerSettings, setProviderSettings] = useState<Record<string, string>>({});
  const [baseUrl, setBaseUrl] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);

  const reload = useCallback(async (auth: string) => {
    const [saved, chosen] = await Promise.all([
      apiRequest<Credential[]>("/api/v1/settings/credentials", auth),
      apiRequest<Record<string, string>>("/api/v1/settings/default-models", auth),
    ]);
    setCredentials(saved); setDefaults(chosen);
    window.dispatchEvent(new Event("nexus:ai-changed")); // the header pill re-reads which model is ready
  }, []);

  useEffect(() => {
    void apiRequest<{ categories: Record<Category, Preset[]> }>("/api/v1/settings/provider-presets", "")
      .then((catalog) => setPresets(Object.values(catalog.categories).flat().filter(preset=>preset.id!=="github_copilot")))
      .catch((reason: unknown) => setError(readError(reason)));
  }, []);
  useEffect(() => {
    if (token) void reload(token).catch((reason: unknown) => setError(readError(reason)));
    else { setCredentials([]); setDefaults({}); setSelected(null); }
  }, [token, reload]);

  const savedByPreset = useMemo(() => new Map(credentials.map((credential) => [credential.preset_id, credential])), [credentials]);
  const openConfigure = (preset: Preset) => {
    const existing = savedByPreset.get(preset.id);
    setSelected(preset); setApiKey(""); setExtraSecrets({}); setProviderSettings(existing?.settings ?? {}); setBaseUrl(existing?.base_url ?? preset.base_url ?? "");
    setIsDefault(existing?.is_default ?? false); setError(""); setNotice(""); setDiscoveredModels([]);
  };
  const requestConfigure = openConfigure;

  const saveAndTest = async () => {
    if (!selected || !token) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const body: Record<string, unknown> = { preset_id: selected.id, base_url: baseUrl || null, is_default: isDefault, default_models: defaults };
      const primaryField = selected.auth_fields.find((field) => field.name === "api_key");
      if (primaryField && apiKey) body.api_key = apiKey;
      const secrets = { ...extraSecrets };
      if (!primaryField && apiKey) {
        const firstSecret = selected.auth_fields.find((field) => field.secret);
        if (firstSecret) secrets[firstSecret.name] = apiKey;
      }
      if (Object.keys(secrets).length > 0) body.secrets = Object.fromEntries(Object.entries(secrets).map(([key, value]) => [key, value]));
      body.settings = providerSettings;
      const credential = await apiRequest<Credential>("/api/v1/settings/credentials", token, { method: "POST", body: JSON.stringify(body) });
      const result = await apiRequest<{ status: string; latency_ms: number; available_models: string[]; balance: Record<string, unknown> | null; error: string | null }>(`/api/v1/settings/credentials/${credential.id}/test`, token, { method: "POST" });
      setNotice(result.status === "CONNECTED" ? t("settings.saved") : result.error ?? "Settings saved; connection needs attention.");
      await reload(token); setSelected(null);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  const saveDefaults = async (next: Record<string, string>) => {
    if (!token) return;
    setDefaults(next);
    try { await apiRequest("/api/v1/settings/default-models", token, { method: "PUT", body: JSON.stringify(next) }); }
    catch (reason) { setError(readError(reason)); }
  };

  const discoverLocalModels = async () => {
    if (!token || !baseUrl) return;
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ available_models: string[] }>("/api/v1/settings/providers/ollama/discover", token, { method: "POST", body: JSON.stringify({ base_url: baseUrl }) });
      setDiscoveredModels(result.available_models); setNotice(`${result.available_models.length} local models discovered.`);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  const shop = savedByPreset.get("shopaikey");
  const presetModels = presets.flatMap((preset) => preset.models.map((model) => ({ ...model, value: modelReference(preset, model), label: `${preset.name} · ${model.id}` })));
  const customModels = credentials.flatMap((credential) => {
    const preset = presets.find((item) => item.id === credential.preset_id);
    if (!preset || !(preset.category === "subscription" || preset.id === "shopaikey")) return [];
    return credential.available_models.filter((id) => !preset.models.some((model) => model.id === id)).map((id) => { const model: Model = { id, kind: "chat", prompt_usd_per_million: null, completion_usd_per_million: null }; return { ...model, value: modelReference(preset, model), label: `${preset.name} · ${id}` }; });
  });
  const allModels = [...presetModels, ...customModels];
  const card = (preset: Preset) => { const saved = savedByPreset.get(preset.id); return <article className="provider-card" key={preset.id}><div className="provider-card-top"><span className="provider-icon">{preset.icon}</span><span className={`provider-status provider-status--${saved?.status.toLowerCase() ?? "unconfigured"}`}>{saved ? saved.status === "CONNECTED" ? t("common.connected") : saved.status : t("common.notAdded")}</span></div><h3>{preset.name}</h3><p>{preset.description}</p>{saved?.masked_key && <div className="provider-masked-key">{saved.masked_key}</div>}<button className="button button-quiet provider-configure" onClick={() => requestConfigure(preset)}>{saved ? t("settings.manage") : preset.local ? t("settings.connectLocal") : t("settings.addKey")}</button></article>; };
  return <main className="provider-settings">
    <header className="provider-page-header"><div><h1>{t("settings.title")}</h1><p>{t("settings.subtitle")}</p></div></header>
    {error && <div className="provider-alert provider-alert--error" role="alert">{error}</div>}
    {notice && <div className="provider-alert" role="status">{notice}</div>}
    <section className="settings-section"><header><span className="step-badge">1</span><div><h2>{t("accounts.title")}</h2><p>{t("accounts.description")}</p></div></header>
      <SubscriptionHub token={token} credentials={credentials} onChanged={() => token ? reload(token) : Promise.resolve()} hideHeading /></section>
    <section className="settings-section settings-section--recommended"><header><span className="step-badge">2</span><div><h2>{t("settings.s2.title")}</h2><p>{t("settings.s2.body")}</p></div></header>
      <HarnessCard token={token} saved={shop} onChanged={() => token ? reload(token) : Promise.resolve()} /></section>
    <section className="settings-section"><header><span className="step-badge">3</span><div><h2>{t("settings.s3.title")}</h2><p>{t("settings.s3.body")}</p></div></header>
      <div className="provider-card-grid">{OTHER_MODEL_PRESETS.map((id) => presets.find((preset) => preset.id === id)).filter((preset): preset is Preset => preset !== undefined).map(card)}</div></section>
    <section className="settings-section settings-expert"><label className="switch-row"><input type="checkbox" checked={expert} onChange={(event) => changeExpert(event.target.checked)} /><span><strong>{t("settings.expert.title")}</strong><small>{t("settings.expert.body")}</small></span></label>
      {expert && <div className="expert-panel">
        <div className="expert-links"><button className="button button-quiet" onClick={() => onNavigate("intelligence")}>{t("settings.expert.metrics")}</button><button className="button button-quiet" onClick={() => onNavigate("teammates")}>{t("settings.expert.teammates")}</button></div>
        {token && <section className="provider-defaults"><div className="provider-section-heading"><div><span className="eyebrow">MODEL ROUTING</span><h2>{t("settings.defaults")}</h2></div></div>
          <div className="provider-default-grid">{modelRoles.map(([key, label, kind]) => <label className="provider-field" key={key}><span>{label}</span><select value={defaults[key] ?? ""} onChange={(event) => void saveDefaults({ ...defaults, [key]: event.target.value })}><option value="">{t("common.auto")}</option>{allModels.filter((model) => model.kind === kind).map((model) => <option key={`${model.label}-${model.id}`} value={model.value}>{model.label}</option>)}</select></label>)}</div></section>}
        {marketplaceCategories.map((category) => <section className="provider-category" key={category}><div className="provider-section-heading"><div><span className="eyebrow">{t("settings.allProviders")}</span><h2>{categoryNames[category]}</h2></div></div><div className="provider-card-grid">{presets.filter((preset) => preset.category === category).map(card)}</div></section>)}
      </div>}
    </section>
    {selected && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}><section className="modal-card provider-modal" role="dialog" aria-modal="true" aria-label={`Configure ${selected.name}`}><header className="modal-head"><div><span className="eyebrow">{t("settings.providerEyebrow")}</span><h2>{selected.name}</h2></div><button className="icon-button" aria-label={t("common.close")} onClick={() => setSelected(null)}>×</button></header><p className="dialog-copy">Endpoint and supported model details are prefilled from the provider preset. Credentials are encrypted and only shown masked.</p><label className="field"><span>{selected.auth_fields.some((field) => field.name === "base_url" && field.required) ? "API URL · required" : "Base URL"}</span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="Provider endpoint" /></label>{selected.auth_fields.filter((field) => field.secret).map((field) => <label className="field" key={field.name}><span>{field.label}{field.required ? " · required" : ""}</span><input type="password" autoComplete="off" value={field.name === "api_key" ? apiKey : extraSecrets[field.name] ?? ""} onChange={(event) => field.name === "api_key" ? setApiKey(event.target.value) : setExtraSecrets({ ...extraSecrets, [field.name]: event.target.value })} placeholder={savedByPreset.has(selected.id) ? "Leave blank to keep the saved value" : field.placeholder || "Paste credential"} /></label>)}{selected.auth_fields.filter((field) => !field.secret && field.name !== "base_url").map((field) => <label className="field" key={field.name}><span>{field.label}{field.required ? " · required" : ""}</span><input value={providerSettings[field.name] ?? ""} onChange={(event) => setProviderSettings({ ...providerSettings, [field.name]: event.target.value })} placeholder={field.placeholder || ""} /></label>)}{selected.local && selected.id === "ollama" && <><button className="button button-quiet" disabled={busy || !token} onClick={() => void discoverLocalModels()}>{busy ? "Checking local server…" : "Discover local models"}</button>{discoveredModels.length > 0 && <div className="provider-model-tags provider-discovered">{discoveredModels.map((model) => <span key={model}>{model}</span>)}</div>}</>}{selected.models.length > 0 && <div className="provider-modal-models"><span>Supported models and configured rates</span>{selected.models.map((model) => <div key={model.id}><code>{model.id}</code><small>{model.prompt_usd_per_million === null ? "Rate follows provider schedule" : `$${model.prompt_usd_per_million} input / $${model.completion_usd_per_million ?? "0"} output per 1M tokens`}</small></div>)}</div>}<label className="provider-toggle provider-toggle--modal"><input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} /><span>{t("settings.makeDefault")}</span></label>{error && <p className="inline-error">{error}</p>}<div className="dialog-actions"><button className="button button-quiet" onClick={() => setSelected(null)}>{t("common.cancel")}</button><button className="button button-primary" disabled={busy || (!selected.local && !apiKey && Object.keys(extraSecrets).length === 0 && !savedByPreset.has(selected.id))} onClick={() => void saveAndTest()}>{busy ? t("common.checking") : t("settings.checkSave")}</button></div></section></div>}
  </main>;
}
