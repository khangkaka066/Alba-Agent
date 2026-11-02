"use client";

import { useEffect, useRef, useState } from "react";
import { ApprovalCard } from "@/components/teammates/approval-card";
import { useLocale } from "@/components/locale-provider";
import { ModelPicker } from "@/components/model-picker";
import { apiRequest } from "@/lib/api";
import { channelList, channelsToConnect } from "@/lib/channels.mjs";
import { getDesktop } from "@/lib/desktop";
import { failureDetails, failureFacts } from "@/lib/history.mjs";
import { classifyArtifact, isFinished, liveActivity, stepLabel } from "@/lib/workspace.mjs";
import { AttachmentBar, atWordStart } from "./attachments";
import { FileGlyph } from "./file-glyph";
import { useWorkspace, type ChatMessage } from "./workspace-context";

/** What to do with a finished task's results: give them to the next team, or start something new from them. */
function HandoffActions() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const go = (studioId: string, promptKey: string) => void workspace.startTask(t(promptKey), "standard", { studioId });
  return <div className="handoff" role="group" aria-label={t("handoff.title")}>
    <span className="handoff__label">{t("handoff.title")}</span>
    <div className="handoff__buttons">
      <button type="button" className="button button-quiet" disabled={workspace.busy} onClick={() => go("marketing-social-publishing-studio", "handoff.marketingPrompt")}>🚀 {t("handoff.marketing")}</button>
      <button type="button" className="button button-quiet" disabled={workspace.busy} onClick={() => go("analytics-optimization-studio", "handoff.analyticsPrompt")}>📊 {t("handoff.analytics")}</button>
      <button type="button" className="button button-quiet" onClick={() => window.dispatchEvent(new Event("nexus:focus-composer"))}>🔗 {t("handoff.custom")}</button>
    </div>
  </div>;
}

/** Why the team stopped, where, and the two ways to carry on. */
function FailureCard() {
  const { t } = useLocale();
  const { failure, retry } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const facts = failureFacts(failure);
  const go = async (mode: "step" | "team") => { setBusy(true); try { await retry(mode); } finally { setBusy(false); } };
  return <div className="failure-card" role="alert">
    <strong>{t("failure.title")}</strong>
    {facts.length === 0 ? <p>{t("failure.unknown")}</p> : <dl>{facts.map((fact) => <div key={fact.key}><dt>{t(`failure.${fact.key}`)}</dt><dd>{fact.value}</dd></div>)}</dl>}
    {failure && <details><summary>{t("failure.details")}</summary><pre>{failureDetails(failure)}</pre></details>}
    <div className="failure-card__actions">
      <button type="button" className="button button-primary" disabled={busy} onClick={() => void go("step")}>{t("failure.retryStep")}</button>
      <button type="button" className="button button-quiet" disabled={busy} onClick={() => void go("team")}>{t("failure.retryTeam")}</button>
    </div>
  </div>;
}

function TeamPill({ message }: { message: ChatMessage }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const active = message.runId === workspace.runId;
  const [open, setOpen] = useState(true);
  const { run, team, token } = workspace;
  const status = active ? run.status : "completed";
  const who = team.crews > 1 ? t("chat.departments", { count: team.crews }) : team.agents ? t("chat.agents", { count: team.agents }) : t("chat.team");
  return <article className={`team-pill ${active ? "is-active" : ""}`} aria-label={t("chat.teamWorking")}>
    <button className="team-pill-head" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
      <span className={`run-dot run-dot--${status}`} />
      <span className="team-pill-title">⚡ {who} {t(`run.word.${status}`) === `run.word.${status}` ? status : t(`run.word.${status}`)}{status === "running" ? "…" : ""}</span>
      <span className="team-pill-caret" aria-hidden="true">{open ? "▾" : "▸"}</span>
    </button>
    <p className="team-pill-line">{active && team.steps ? stepLabel(run, team.steps, t) : message.text}</p>
    {!active && message.runId && message.workflowId && <button type="button" className="link-button" onClick={() => workspace.openRun(message.workflowId as string, message.runId as string, message.text)}>{t("chat.openTask")}</button>}
    {open && active && <>
      <p className="team-pill-activity">{liveActivity(run, t)}</p>
      {run.tools.length > 0 && <div className="chip-row">{run.tools.slice(-4).map((tool) => <span className="chip" key={tool.id}>{tool.name}</span>)}</div>}
      {workspace.artifacts.length > 0 && <div className="chip-row" aria-label={t("common.files", { count: workspace.artifacts.length })}>{workspace.artifacts.slice(0, 8).map((file) => <span className="chip-pair" key={file.filename}>
        <button className="chip chip--file" onClick={() => { workspace.select(file.filename); workspace.setView("workbench"); }}>
          <FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} />{file.filename}</button>
        <button className="chip chip--download" aria-label={t("stage.downloadFile", { name: file.filename })} title={t("stage.download")} onClick={() => void workspace.download(file)}>↓</button></span>)}</div>}
      {status === "completed" && workspace.artifacts.length > 0 && <HandoffActions />}
      {status === "failed" && <FailureCard />}
      {run.approvals.map((approval) => <ApprovalCard key={approval.approval_id} approval={approval} token={token} onResolved={workspace.dismissApproval} />)}
    </>}
  </article>;
}

type Pending = { proposals: number; recommendations: number };

/** Learning, self-healing and distillation run on their own; this only says so when something is ready to act on. */
/** Shown only for a team that publishes (its spec declares channels) and only until those channels are connected. */
function ChannelsHint({ onOpen }: { onOpen: () => void }) {
  const { t } = useLocale();
  const { token, spec, workflowId } = useWorkspace();
  const [credentials, setCredentials] = useState<unknown[] | null>(null);
  const [dismissed, setDismissed] = useState("");
  const wanted = channelsToConnect(spec, []);
  useEffect(() => {
    if (!token || wanted.length === 0) return;
    let stopped = false;
    void apiRequest<unknown[]>("/api/v1/settings/credentials", token).then((value) => { if (!stopped) setCredentials(value); }).catch(() => undefined);
    return () => { stopped = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, workflowId, wanted.length]);
  const missing = credentials === null ? [] : channelsToConnect(spec, credentials);
  if (missing.length === 0 || dismissed === workflowId) return null;
  return <div className="insight-banner" role="status">
    <span>{t("chat.channelsHint", { channels: channelList(missing) })}</span>
    <button className="link-button" onClick={onOpen}>{t("chat.channelsAction")}</button>
    <button className="insight-banner__close" aria-label={t("common.close")} onClick={() => setDismissed(workflowId ?? "")}>×</button>
  </div>;
}

function InsightBanner({ onOpen }: { onOpen: () => void }) {
  const { t } = useLocale();
  const { token, runId, run } = useWorkspace();
  const [pending, setPending] = useState<Pending>({ proposals: 0, recommendations: 0 });
  const [dismissed, setDismissed] = useState("");
  const finished = isFinished(run.status);
  useEffect(() => {
    if (!finished || !token) return;
    let stopped = false;
    void Promise.all([
      apiRequest<unknown[]>("/api/v1/self-healing/proposals", token).catch(() => []),
      apiRequest<Array<{ status: string }>>("/api/v1/analytics/distillation/recommendations", token).catch(() => []),
    ]).then(([proposals, recommendations]) => { if (!stopped) setPending({ proposals: proposals.length, recommendations: recommendations.filter((item) => item.status === "pending").length }); });
    return () => { stopped = true; };
  }, [finished, runId, token]);
  if (!finished || dismissed === runId || pending.proposals + pending.recommendations === 0) return null;
  return <div className="insight-banner" role="status">
    <span>{t("chat.insight")}</span>
    <button className="link-button" onClick={onOpen}>{t("common.view")}</button>
    <button className="insight-banner__close" aria-label={t("common.close")} onClick={() => setDismissed(runId ?? "")}>×</button>
  </div>;
}

/** Left pane of the active studio: the conversation, approvals, and a box for follow-ups. */
export function Composer({ onNavigate }: { onNavigate: (page: "intelligence" | "integrations" | "settings") => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [text, setText] = useState("");
  const [picking, setPicking] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const focus = () => field.current?.focus();
    window.addEventListener("nexus:focus-composer", focus);
    return () => window.removeEventListener("nexus:focus-composer", focus);
  }, []);
  const desktop = getDesktop();
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight }); }, [workspace.messages.length, workspace.run.thoughts.length, workspace.run.approvals.length]);
  const working = workspace.busy || (workspace.runId !== null && !isFinished(workspace.run.status));

  const submit = () => {
    const prompt = text.trim();
    if (!prompt || workspace.busy) return;
    setText("");
    void workspace.startTask(prompt, "auto");
  };

  return <div className="composer">
    <header className="composer-head"><strong>{t("chat.title")}</strong>
      <button className="button button-quiet composer-new" onClick={workspace.newTask}>{t("chat.newTask")}</button></header>
    <div className="composer-stream" ref={list} aria-live="polite">
      {workspace.messages.map((message) => message.role === "user"
        ? <div className="bubble bubble--user" key={message.id}>{message.text}{message.attached && message.attached.length > 0 && <small className="bubble__attached">📎 {message.attached.join(", ")}</small>}</div>
        : message.role === "team" ? <TeamPill key={message.id} message={message} />
        : <p className="bubble bubble--note" key={message.id} role="status">{message.text}</p>)}
      <ChannelsHint onOpen={() => onNavigate("integrations")} />
      <InsightBanner onOpen={() => onNavigate("intelligence")} />
    </div>
    <form className="composer-input" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      {desktop && workspace.folder && <span className="composer-folder" title={workspace.folder.root}>{t("chat.workingIn", { name: workspace.folder.name, count: workspace.folder.files.length })}</span>}
      <textarea ref={field} aria-label={t("chat.followUp")} rows={2} value={text} disabled={workspace.busy}
        placeholder={t(working ? "chat.busyPlaceholder" : "chat.followUpPlaceholder")}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => { if (event.key === "@" && atWordStart(event.currentTarget)) { event.preventDefault(); setPicking(true); return; } if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); } }} />
      <AttachmentBar open={picking} onOpenChange={setPicking} />
      <div className="composer-actions"><ModelPicker compact disabled={workspace.busy} onOpenSettings={() => onNavigate("settings")} /><span>{t("chat.keys")}</span>
        <button className="send-button" type="submit" aria-label={t("common.send")} disabled={!text.trim() || workspace.busy || !workspace.token}>↑</button></div>
    </form>
  </div>;
}
