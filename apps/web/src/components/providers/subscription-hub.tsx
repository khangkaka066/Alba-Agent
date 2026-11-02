"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest, readError } from "@/lib/api";
import { billingLabel, expiryLabel, groupDeviceCode, mountedSummary, nextPollSeconds, verifySummary } from "@/lib/subscriptions.mjs";
import type { MountedLogin, VerifyResult } from "@/lib/subscriptions.mjs";

type Connector = {
  id: string; name: string; vendor: string; provider: string; description: string; plans: string[]; auth_methods: string[];
  models: string[]; credential_hint: string; needs_base_url: boolean; base_url: string | null; notice: string; mounted: MountedLogin;
};
export type PlanCredential = { id: string; preset_id: string; status: string; base_url: string | null; is_default: boolean; available_models: string[]; settings: Record<string, string>; safe_error: string | null };
type DeviceFlow = { flow_id: string; user_code: string; verification_uri: string; expires_in: number; interval: number };
type PollResult = { status: "pending" | "slow_down" | "authorized" | "expired" | "denied"; interval?: number | null };

const SUBSCRIPTIONS = "/api/v1/settings/subscriptions";

export function SubscriptionHub({ token, credentials, onChanged, hideHeading = false }: { token: string; credentials: PlanCredential[]; onChanged: () => Promise<void>; hideHeading?: boolean }) {
  const { t } = useLocale();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [paste, setPaste] = useState<Connector | null>(null);
  const [content, setContent] = useState("");
  const [bridgeUrl, setBridgeUrl] = useState("");
  const [device, setDevice] = useState<DeviceFlow | null>(null);
  const [deviceNote, setDeviceNote] = useState("");
  const [models, setModels] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, VerifyResult>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const poller = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => { if (poller.current) clearTimeout(poller.current); poller.current = null; }, []);
  useEffect(() => stopPolling, [stopPolling]);
  useEffect(() => {
    if (!token) { setConnectors([]); return; }
    void apiRequest<{ connectors: Connector[] }>(`${SUBSCRIPTIONS}/connectors`, token)
      .then((catalog) => setConnectors(catalog.connectors))
      .catch((reason: unknown) => setError(readError(reason)));
  }, [token]);

  const credentialFor = (connector: Connector) => credentials.find((item) => item.preset_id === connector.id);

  const verify = async (credential: PlanCredential, connector: Connector, model?: string) => {
    setBusy(`verify:${connector.id}`); setError("");
    try {
      const chosen = model ?? models[credential.id] ?? credential.available_models[0];
      const result = await apiRequest<VerifyResult>(`${SUBSCRIPTIONS}/credentials/${credential.id}/verify`, token, { method: "POST", body: JSON.stringify({ model: chosen }) });
      setResults((current) => ({ ...current, [credential.id]: result }));
      await onChanged();
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(""); }
  };

  const importLogin = async (connector: Connector, source: "mounted" | "paste") => {
    setBusy(`import:${connector.id}`); setError("");
    try {
      const body = { connector_id: connector.id, source, is_default: true, ...(source === "paste" ? { content } : {}), ...(bridgeUrl ? { base_url: bridgeUrl } : {}) };
      const credential = await apiRequest<PlanCredential>(`${SUBSCRIPTIONS}/import`, token, { method: "POST", body: JSON.stringify(body) });
      setPaste(null); setContent(""); setBridgeUrl("");
      await onChanged();
      await verify(credential, connector);
    } catch (reason) { setError(readError(reason)); setBusy(""); }
  };

  const pollDevice = useCallback((flow: DeviceFlow, connector: Connector, seconds: number) => {
    stopPolling();
    poller.current = setTimeout(async () => {
      try {
        const result = await apiRequest<PollResult & { credential?: PlanCredential }>(`${SUBSCRIPTIONS}/github-copilot/device/poll`, token, { method: "POST", body: JSON.stringify({ flow_id: flow.flow_id, is_default: true }) });
        if (result.status === "authorized" && result.credential) {
          setDevice(null); setDeviceNote("");
          await onChanged();
          await verify(result.credential, connector);
        } else if (result.status === "expired" || result.status === "denied") {
          setDevice(null); setDeviceNote(result.status === "denied" ? "Sign-in was cancelled on GitHub." : "The code expired. Start again.");
        } else pollDevice(flow, connector, nextPollSeconds(flow.interval, result.status, result.interval));
      } catch (reason) { setDevice(null); setError(readError(reason)); }
    }, seconds * 1000);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, stopPolling, onChanged]);

  const startDevice = async (connector: Connector) => {
    setBusy(`device:${connector.id}`); setError(""); setDeviceNote("");
    try {
      const flow = await apiRequest<DeviceFlow>(`${SUBSCRIPTIONS}/github-copilot/device/start`, token, { method: "POST" });
      setDevice(flow);
      pollDevice(flow, connector, flow.interval);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(""); }
  };

  const hint = (connector: Connector) => t(connector.id === "github_copilot" ? "common.notSignedIn" : "common.notConnected");

  return <section className="plan-hub">
    {!hideHeading && <div className="provider-section-heading"><div><span className="eyebrow">MONTHLY PLANS</span><h2>Connect a subscription plan</h2></div><span className="provider-caption">Usage covered by your plan is recorded at $0 per token.</span></div>}
    {error && <div className="provider-alert provider-alert--error" role="alert">{error}</div>}
    <div className="provider-card-grid plan-grid">{connectors.map((connector) => {
      const saved = credentialFor(connector);
      const summary = mountedSummary(connector.mounted);
      const result = saved ? results[saved.id] : undefined;
      const outcome = verifySummary(result);
      const chosenModel = saved ? models[saved.id] ?? saved.available_models[0] ?? "" : "";
      return <article className="provider-card plan-card" key={connector.id} data-connector={connector.id}>
        <div className="provider-card-top"><span className="plan-vendor">{connector.vendor}</span><span className={`provider-status provider-status--${saved ? saved.status.toLowerCase() : "unconfigured"}`}>{saved ? saved.status : hint(connector)}</span></div>
        <h3>{connector.name}</h3>
        <p className="plan-description">{connector.description}</p>
        <div className="provider-model-tags">{connector.plans.map((plan) => <span key={plan}>{plan}</span>)}</div>
        {token && !saved && <p className={`plan-mounted plan-mounted--${summary.tone}`}>{connector.id === "github_copilot" ? summary.tone === "ok" ? summary.text : "Sign in with a GitHub device code." : summary.text}</p>}
        {saved && <p className="plan-billing">{billingLabel(saved.settings)}{saved.settings.plan ? ` · ${saved.settings.plan}` : ""}{saved.settings.expires_at ? ` · ${expiryLabel(saved.settings.expires_at)}` : ""}</p>}
        {connector.notice && <p className="plan-notice">{connector.notice}</p>}
        {saved && <label className="provider-field plan-model"><span>Model to test</span>
          <select value={chosenModel} onChange={(event) => setModels({ ...models, [saved.id]: event.target.value })}>{saved.available_models.map((model) => <option key={model} value={model}>{model}</option>)}</select></label>}
        {outcome && <p className={`plan-result plan-result--${outcome.tone}`} role="status">{outcome.text}</p>}
        {saved?.safe_error && !outcome && <p className="plan-result plan-result--bad">{saved.safe_error}</p>}
        <div className="plan-actions">
          {saved && <button className="button button-primary" disabled={busy !== "" || !token} onClick={() => void verify(saved, connector)}>{busy === `verify:${connector.id}` ? "Testing…" : "Verify Subscription & Test Model"}</button>}
          {token && connector.id === "github_copilot" && <button className="button button-quiet" disabled={busy !== "" || device !== null} onClick={() => void startDevice(connector)}>{saved ? "Sign in again" : "Sign in with GitHub"}</button>}
          {token && summary.tone === "ok" && connector.id !== "github_copilot" && <button className="button button-quiet" disabled={busy !== ""} onClick={() => void importLogin(connector, "mounted")}>{busy === `import:${connector.id}` ? "Connecting…" : "Use detected login"}</button>}
          {token && connector.id !== "github_copilot" && <button className="button button-quiet" disabled={busy !== ""} onClick={() => { setPaste(connector); setContent(""); setBridgeUrl(saved?.base_url && connector.needs_base_url ? saved.base_url : ""); setError(""); }}>Paste token / file</button>}
          
        </div>
        {device && connector.id === "github_copilot" && <div className="device-code" role="status">
          <span>Enter this code on GitHub</span>
          <strong aria-label="GitHub device code">{groupDeviceCode(device.user_code)}</strong>
          <a href={device.verification_uri} target="_blank" rel="noreferrer">{device.verification_uri.replace("https://", "")}</a>
          <small>Waiting for you to approve… this page continues on its own.</small>
          <button className="button button-quiet" onClick={() => { stopPolling(); setDevice(null); }}>Cancel</button>
        </div>}
        {deviceNote && connector.id === "github_copilot" && <p className="plan-result plan-result--bad">{deviceNote}</p>}
      </article>;
    })}</div>
    {paste && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPaste(null); }}>
      <section className="modal-card provider-modal" role="dialog" aria-modal="true" aria-label={`Connect ${paste.name}`}>
        <header className="modal-head"><div><span className="eyebrow">SUBSCRIPTION PLAN</span><h2>{paste.name}</h2></div><button className="icon-button" aria-label="Close" onClick={() => setPaste(null)}>×</button></header>
        <p className="dialog-copy">{paste.credential_hint}. It is encrypted for this workspace and shown only as a masked value.</p>
        <label className="field"><span>Token or credential file · required</span><textarea className="plan-textarea" rows={6} autoComplete="off" spellCheck={false} value={content} onChange={(event) => setContent(event.target.value)} placeholder="Paste the token, or the whole JSON file" /></label>
        <label className="field"><span>{paste.needs_base_url ? "Subscription bridge URL · required for plan tokens" : "Subscription bridge URL · optional"}</span><input value={bridgeUrl} onChange={(event) => setBridgeUrl(event.target.value)} placeholder={paste.base_url ?? "https://bridge.example/v1"} /></label>
        {paste.notice && <p className="plan-notice">{paste.notice}</p>}
        {error && <p className="inline-error">{error}</p>}
        <div className="dialog-actions"><button className="button button-quiet" onClick={() => setPaste(null)}>Cancel</button><button className="button button-primary" disabled={busy !== "" || !content.trim()} onClick={() => void importLogin(paste, "paste")}>{busy ? "Connecting…" : "Connect & Verify"}</button></div>
      </section>
    </div>}
  </section>;
}
