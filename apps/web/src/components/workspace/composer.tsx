"use client";

import { useEffect, useRef, useState } from "react";
import { ApprovalCard } from "@/components/teammates/approval-card";
import { useLocale } from "@/components/locale-provider";
import { apiRequest } from "@/lib/api";
import { channelList, channelsToConnect } from "@/lib/channels.mjs";
import { failureDetails, failureFacts } from "@/lib/history.mjs";
import { classifyArtifact, isFinished } from "@/lib/workspace.mjs";
import { FileGlyph } from "./file-glyph";
import { Icon, type IconName } from "@/components/shell/icons";
import { useShell } from "@/components/shell/shell-context";
import { isHtmlArtifact } from "./html-artifact-preview";
import { ActivityLog } from "./activity-log";
import { MessageContent } from "./message-content";
import { PromptBox } from "./prompt-box";
import { CheckpointActions, LiveAgentTree, specNodes } from "./run-artifacts";
import { ImplementationPlanArtifact, ProposalCard } from "./plan-proposal";
import { useWorkspace, type ChatMessage } from "./workspace-context";

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

export function UnifiedRunCard({ message }: { message: ChatMessage }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const { run, token, team } = workspace;
  const active = message.runId === workspace.runId;
  const nodes = specNodes(workspace.spec).filter((node) => node.kind !== "start");
  const roles = nodes.flatMap((node) => Array.isArray(node.agents) ? node.agents.map((agent) => String((agent as Record<string, unknown>).role ?? "")) : []);
  const done = run.status === "completed" ? nodes.length : nodes.filter((node) => run.completed.includes(String(node.id))).length;
  const finished = isFinished(run.status);
  const preview = (file: typeof workspace.artifacts[number]) => { workspace.select(file.filename); workspace.setArtifactView("preview"); shell.showDock(isHtmlArtifact(file) ? "browser" : "files"); };
  const diff = (file: typeof workspace.artifacts[number]) => { workspace.select(file.filename); workspace.setArtifactView("diff"); shell.showDock("files"); };
  if (!active) return <button type="button" className="ag-past-run" onClick={() => { if (message.runId && message.workflowId) workspace.openRun(message.workflowId, message.runId, message.text); }}>{message.text}<Icon name="chevronRight" size={14} /></button>;
  return <article className="ag-run-conversation ag-unified-run" aria-label={t("result.card")}>
    {!finished && <header className="ag-run-heading"><span className={`run-dot run-dot--${run.status}`} /><strong>{t(`result.status.${run.status}`)}</strong>{nodes.length > 1 && <span className="ag-run-step-count">{done}/{nodes.length} {t("result.steps")}</span>}<button type="button" className="ag-run-detail" onClick={() => shell.showDock("agents")}>{t(team.agents === 1 ? "result.agentOne" : "result.agents", { count: team.agents })}</button></header>}
    <ActivityLog />
    {run.status === "completed" && workspace.resultText && <div className="ag-result-summary"><MessageContent text={workspace.resultText} /><CopyButton text={workspace.resultText} /></div>}
    {run.status === "completed" && !workspace.resultText && workspace.artifacts.length === 0 && <p className="nx-stopped"><Icon name="check" size={13} /> {t("result.status.completed")}</p>}
    {workspace.artifacts.length > 0 && <div className="ag-delivered-files">{workspace.artifacts.map((file) => <div className="ag-result-file" key={file.filename}>
      <button type="button" className="ag-result-filename" onClick={() => preview(file)}><FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} /><span>{file.filename}</span><small>{(file.size_bytes / 1024).toFixed(1)} KB</small></button>
      <div className="ag-result-actions"><button type="button" className="button button-primary" onClick={() => preview(file)}><Icon name="globe" size={14} />{t(isHtmlArtifact(file) ? "result.previewLive" : "result.preview")}</button>
      {classifyArtifact(file.filename, file.mime_type).text && <button type="button" className="button button-quiet" onClick={() => diff(file)}><Icon name="review" size={14} />{t("result.diff")}</button>}
      <button type="button" className="button button-quiet" onClick={() => void workspace.download(file)}><Icon name="chevronDown" size={14} />{t("stage.download")}</button></div>
    </div>)}</div>}
    {nodes.length > 1 && <details className="ag-unified-details"><summary>{t(nodes.length === 1 ? "result.detailsOne" : "result.details", { count: nodes.length })}</summary>
      {workspace.spec && <ImplementationPlanArtifact spec={workspace.spec} compact />}
      {team.agents > 2 && <LiveAgentTree />}
      {roles.length > 0 && <p className="nx-plan-roles">{roles.join(" · ")}</p>}
    </details>}
    {run.status === "failed" && <FailureCard />}
    {run.status === "cancelled" && <p className="nx-stopped" role="status">{t("interface.stopped")}</p>}
    {run.approvals.map((approval, index) => <ApprovalCard key={approval.approval_id} approval={approval} token={token} onResolved={workspace.dismissApproval} hotkeys={index === 0} />)}
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

/** What "/" offers at the start of an empty message: the same actions the shortcuts and the title bar reach. */
export function SlashMenu({ onClose }: { onClose: () => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const items: Array<{ icon: IconName; label: string; description: string; run: () => void }> = [
    { icon: "review", label: "/plan", description: t("interface.command.plan"), run: () => workspace.setExecutionMode("plan") },
    { icon: "chat", label: "/chat", description: t("interface.command.ask"), run: () => workspace.setExecutionMode("ask") },
    { icon: "bolt", label: "/agent", description: t("interface.command.agent"), run: () => workspace.setExecutionMode("agent") },
    { icon: "canvas", label: "/teamwork", description: t("interface.command.team"), run: () => { workspace.setExecutionMode("agent"); workspace.setRigor("full_studio"); } },
    { icon: "globe", label: "/browser", description: t("interface.command.browser"), run: () => shell.showDock("browser") },
    { icon: "terminal", label: "/terminal", description: t("interface.command.terminal"), run: () => shell.showDock("terminal") },
    { icon: "log", label: "/schedule", description: t("interface.command.schedule"), run: () => shell.navigate("teammates") },
    { icon: "extensions", label: "/plugin", description: t("interface.command.plugin"), run: () => shell.navigate("integrations") },
  ];
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => { root.current?.querySelector<HTMLButtonElement>("button")?.focus(); }, []);
  const move = (event: React.KeyboardEvent) => {
    const buttons = Array.from(root.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "ArrowDown") { event.preventDefault(); buttons[(at + 1) % buttons.length]?.focus(); }
    else if (event.key === "ArrowUp") { event.preventDefault(); buttons[(at - 1 + buttons.length) % buttons.length]?.focus(); }
    else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); window.dispatchEvent(new Event("nexus:focus-composer")); }
  };
  return <div className="ag-popover ag-popover--up ag-slash" role="menu" aria-label={t("prompt.actions")} ref={root} onKeyDown={move}>
    {items.map((item) => <button key={item.label} type="button" role="menuitem" className="ag-menuitem" onClick={() => { onClose(); item.run(); window.setTimeout(() => window.dispatchEvent(new Event("nexus:focus-composer")), 0); }}><Icon name={item.icon} size={15} /><span><strong>{item.label}</strong><small>{item.description}</small></span></button>)}
  </div>;
}

function CopyButton({ text }: { text: string }) {
  const { t } = useLocale();
  const [done, setDone] = useState(false);
  return <button type="button" className="ag-iconbtn ag-iconbtn--small" aria-label={t("common.copy")} title={t("common.copy")} onClick={() => { void navigator.clipboard.writeText(text).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1500); }).catch(() => undefined); }}><Icon name={done ? "check" : "copy"} size={13} /></button>;
}

function RequestMessage({ message }: { message: ChatMessage }) {
  const { t } = useLocale();
  const [expanded, setExpanded] = useState(false);
  const long = message.text.length > 500 || message.text.split("\n").length > 8;
  return <div className="bubble bubble--user ag-bubble">
    <p className={long && !expanded ? "ag-request-text is-folded" : "ag-request-text"}>{message.text}</p>
    {long && <button type="button" className="ag-run-detail" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{t(expanded ? "activity.hideRequest" : "activity.showRequest")}</button>}
    {message.attached && message.attached.length > 0 && <small className="bubble__attached">{message.attached.join(", ")}</small>}
    <span className="ag-bubble__tools"><CheckpointActions text={message.text} runId={message.checkpoint?.runId} checkpoint={message.checkpoint?.id} /></span>
  </div>;
}

/** The conversation: messages, approvals and the message box at the bottom. */
export function Composer({ onNavigate }: { onNavigate: (page: "intelligence" | "integrations" | "settings") => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [text, setText] = useState("");
  const [slash, setSlash] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  useEffect(() => { if (following.current) { const frame = requestAnimationFrame(() => list.current?.scrollTo({ top: list.current.scrollHeight })); return () => cancelAnimationFrame(frame); } }, [workspace.messages.length, workspace.run.activity.length, workspace.run.approvals.length, workspace.artifacts.length, workspace.run.status]);
  const working = workspace.busy || (workspace.runId !== null && !isFinished(workspace.run.status));

  const submit = () => {
    const prompt = text.trim();
    if (!prompt || workspace.uploading || workspace.uploads.some((item) => item.status === "error")) return;
    setText("");
    workspace.sendTask(prompt, workspace.rigor);
  };

  return <div className="composer ag-conversation">
    <div className="composer-stream" ref={list} aria-live="polite" onScroll={(event) => { const element = event.currentTarget; following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100; }}>
      {workspace.messages.map((message) => message.role === "user"
        ? <RequestMessage key={message.id} message={message} />
        : message.role === "team" ? message.runId ? <UnifiedRunCard key={message.id} message={message} /> : <article className="ag-consult-answer" key={message.id}><MessageContent text={message.text} /><CopyButton text={message.text} /></article>
        : <p className="bubble bubble--note" key={message.id} role="status">{message.text}</p>)}
      {workspace.plan && <div className="nx-plan-card"><Icon name="review" /><div><strong>{String(workspace.plan.spec.name ?? t("studio.implementationPlan"))}</strong><p>{t("interface.planReady")}</p></div><button type="button" className="button button-quiet" onClick={() => { workspace.setMode("mission"); window.dispatchEvent(new Event("nexus:open-artifacts")); }}>{t("interface.reviewPlan")}</button><button type="button" className="button button-primary" disabled={workspace.busy} onClick={() => void workspace.continuePlan([])}>{t("interface.proceed")}</button></div>}
      {workspace.proposal && <ProposalCard proposal={workspace.proposal.card} disabled={workspace.busy}
        onBuild={(answers) => void workspace.answerProposal(answers)} onSkip={() => void workspace.answerProposal(null)} />}
      <ChannelsHint onOpen={() => onNavigate("integrations")} />
      <InsightBanner onOpen={() => onNavigate("intelligence")} />
      {workspace.busy && <div className="nx-responding" role="status" aria-label={t("interface.responding")}><i /><i /><i /></div>}
    </div>
    <form className="ag-composer" onSubmit={(event) => { event.preventDefault(); submit(); }}>
      {workspace.queuedMessages.length > 0 && <div className="nx-message-queue" aria-label={t("settings.queuedMessages")}>{workspace.queuedMessages.map((item, index) => <div key={item.id}><span>{index + 1}</span><p>{item.text}</p><button type="button" className="ag-iconbtn" aria-label={t("settings.removeQueued")} onClick={() => workspace.removeQueuedMessage(item.id)}><Icon name="close" size={13} /></button></div>)}</div>}
      {slash && <SlashMenu onClose={() => { setSlash(false); if (text.trim() === "/") setText(""); }} />}
      <PromptBox value={text} onChange={setText} onSubmit={submit} onSlash={() => setSlash(true)} onOpenSettings={() => onNavigate("settings")} label={t("chat.followUp")}
        placeholder={t(working ? "chat.busyPlaceholder" : "prompt.placeholder")} busy={workspace.busy} canSend={Boolean(text.trim() && workspace.token)} />
    </form>
  </div>;
}
