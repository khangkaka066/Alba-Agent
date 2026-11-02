"use client";

import { useCallback, useEffect, useState } from "react";
import { CapabilityHub } from "@/components/capabilities/capability-hub";
import { useLocale } from "@/components/locale-provider";
import { apiRequest, readError } from "@/lib/api";
import { declaredChannels, visibleChannels } from "@/lib/channels.mjs";

type Channel = { id: string; name: string; descriptionKey: string; icon: string; needsPage: boolean };
type Saved = { id: string; preset_id: string; status: string; safe_error: string | null };

const CHANNELS: Channel[] = [
  { id: "tiktok", name: "TikTok", descriptionKey: "tools.tiktok", icon: "♪", needsPage: false },
  { id: "facebook", name: "Facebook", descriptionKey: "tools.facebook", icon: "f", needsPage: true },
  { id: "youtube", name: "YouTube", descriptionKey: "tools.youtube", icon: "▶", needsPage: false },
];

function ChannelCard({ channel, saved, token, onChanged }: { channel: Channel; saved?: Saved; token: string; onChanged: () => Promise<void> }) {
  const { t } = useLocale();
  const [editing, setEditing] = useState(false);
  const [secret, setSecret] = useState("");
  const [pageId, setPageId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const connected = saved?.status === "connected";

  const connect = async () => {
    setBusy(true); setError("");
    try {
      const credential = await apiRequest<Saved>("/api/v1/settings/credentials", token, { method: "POST", body: JSON.stringify({
        preset_id: channel.id, secrets: { access_token: secret }, settings: channel.needsPage && pageId ? { page_id: pageId } : {}, is_default: false,
      }) });
      await apiRequest(`/api/v1/settings/credentials/${credential.id}/test`, token, { method: "POST" });
      setEditing(false); setSecret(""); await onChanged();
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    if (!saved) return;
    setBusy(true);
    try { await apiRequest(`/api/v1/settings/credentials/${saved.id}`, token, { method: "DELETE" }); await onChanged(); }
    catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  return <article className={`channel-card ${connected ? "is-connected" : ""}`} data-channel={channel.id}>
    <div className="channel-card__top"><span className="channel-icon" aria-hidden="true">{channel.icon}</span>
      <div><h3>{channel.name}</h3><p>{t(channel.descriptionKey)}</p></div>
      <span className={`switch ${connected ? "is-on" : ""}`} role="img" aria-label={t(connected ? "common.connected" : "common.notConnected")}><i /></span></div>
    {saved && !connected && <p className="channel-note">{saved.safe_error ?? t("tools.unverified")}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    {editing && <div className="channel-form">
      <label className="field"><span>Access token</span><input type="password" autoComplete="off" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={t("tools.tokenPlaceholder")} /></label>
      {channel.needsPage && <label className="field"><span>{t("tools.pageId")}</span><input value={pageId} onChange={(event) => setPageId(event.target.value)} /></label>}
      <div className="channel-actions"><button className="button button-quiet" onClick={() => setEditing(false)}>{t("common.cancel")}</button><button className="button button-primary" disabled={busy || !secret.trim()} onClick={() => void connect()}>{busy ? t("common.checking") : t("common.saveCheck")}</button></div>
    </div>}
    {!editing && <div className="channel-actions">
      {saved && <button className="button button-quiet" disabled={busy} onClick={() => void disconnect()}>{t("tools.disconnect")}</button>}
      <button className={`button ${connected ? "button-quiet" : "button-primary"}`} onClick={() => setEditing(true)}>{saved ? t("tools.changeToken") : t("common.connect")}</button>
    </div>}
  </article>;
}

export function IntegrationsPage({ token, onConnect }: { token: string; onConnect: () => void }) {
  const { t } = useLocale();
  const [saved, setSaved] = useState<Saved[]>([]);
  const [declared, setDeclared] = useState<string[]>([]);
  const load = useCallback(async () => {
    if (!token) return;
    setSaved(await apiRequest<Saved[]>("/api/v1/settings/credentials", token));
  }, [token]);
  useEffect(() => { void load().catch(() => undefined); }, [load]);
  // Channels only matter to a team that publishes, so they appear once the workspace has one.
  useEffect(() => {
    if (!token) return;
    void apiRequest<unknown[]>("/api/v1/workflows", token).then((workflows) => setDeclared(declaredChannels(workflows))).catch(() => undefined);
  }, [token]);
  const [expert, setExpert] = useState(false);
  useEffect(() => { try { setExpert(window.localStorage.getItem("nexus_expert_mode") === "1"); } catch { /* storage blocked: documents stay hidden */ } }, []);
  const shown = visibleChannels(declared, saved.map((item) => item.preset_id));

  return <div className="page-body tools-page">
    <div className="page-title-row"><div><h1>{t("integrations.title")}</h1><p>{t("integrations.subtitle")}</p></div></div>
    {shown.length > 0 && <section className="tools-section"><header><h2>{t("tools.channels")}</h2><p>{t("tools.channelsBody")}</p></header>
      <div className="channel-grid">{CHANNELS.filter((channel) => shown.includes(channel.id as never)).map((channel) => <ChannelCard key={channel.id} channel={channel} saved={saved.find((item) => item.preset_id === channel.id)} token={token} onChanged={load} />)}</div>
      <p className="channel-footnote">{t("tools.footnote")}</p>
    </section>}
    <section className="tools-section"><header><h2>{t("tools.skillsHeading")}</h2></header>
      <CapabilityHub token={token} onConnect={onConnect} tabs={expert ? ["skills", "tools", "knowledge"] : ["skills", "tools"]} />
    </section>
  </div>;
}
