"use client";

import { useEffect, useRef, useState } from "react";
import { WorkflowStudio } from "@/components/canvas/workflow-studio";
import { LiveInspector } from "@/components/inspector/live-inspector";
import type { PendingApproval } from "@/components/teammates/approval-card";
import { useLocale } from "@/components/locale-provider";
import { FileGlyph } from "@/components/workspace/file-glyph";
import { TerminalPanel } from "@/components/workspace/terminal-panel";
import { DiffView } from "@/components/workspace/diff-view";
import { Workbench } from "@/components/workspace/workbench";
import { ArtifactDock, specNodes } from "@/components/workspace/run-artifacts";
import { useComputer } from "@/components/workspace/use-computer";
import { HtmlArtifactPreview, isHtmlArtifact } from "@/components/workspace/html-artifact-preview";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { apiRequest, readError } from "@/lib/api";
import { normalizeUrl, type DockTab } from "@/lib/shell.mjs";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { rememberBrowserUrl } from "@/lib/preferences.mjs";
import { Icon, type IconName } from "./icons";
import { useShell } from "./shell-context";
import { PanelResize } from "./panel-resize";

const TAB_ICONS: Record<DockTab, IconName> = { artifacts: "file", agents: "canvas", tasks: "log", review: "review", files: "file", terminal: "terminal", browser: "globe", canvas: "canvas" };
const PRIMARY_TABS: DockTab[] = ["artifacts", "agents", "tasks", "review", "terminal"];

function AgentsTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const nodes = specNodes(workspace.spec);
  const agents = nodes.flatMap((node) => (Array.isArray(node.agents) ? node.agents : node.kind === "sandbox" ? [{ role: t("studio.coder") }, { role: t("studio.reviewer") }] : []).map((agent) => ({ node, agent: agent as Record<string, unknown> })));
  if (!agents.length) return <div className="nx-pane-empty"><Icon name="canvas" size={26} /><h3>{t("interface.noAgents")}</h3><p>{t("interface.noAgentsBody")}</p></div>;
  return <div className="nx-agent-list"><p className="nx-pane-description">{t("interface.agentsBody")}</p>{agents.map(({ node, agent }, index) => {
    const id = String(node.id), done = workspace.run.status === "completed" || workspace.run.completed.includes(id), active = workspace.run.active.includes(id);
    return <button type="button" key={`${id}/${index}`} className="nx-agent-row" onClick={() => workspace.focusNode(id)}><span className="nx-agent-avatar">{String(agent.role ?? "A").slice(0, 1)}</span><span><strong>{String(agent.role ?? node.label)}</strong><small>{String(node.label ?? "")}</small><small>{t(done ? "studio.done" : active ? "studio.inProgress" : "studio.pending")}</small></span><Icon name="chevronRight" size={14} /></button>;
  })}</div>;
}

function BackgroundTasksTab() {
  const { t } = useLocale();
  const shell = useShell();
  const computer = useComputer(true, false);
  const tasks = computer.session?.processes.filter((process) => process.background) ?? [];
  if (!tasks.length) return <div className="nx-pane-empty"><Icon name="terminal" size={26} /><h3>{t("interface.noTasks")}</h3><p>{t("interface.noTasksBody")}</p>{computer.error && <p role="alert">{computer.error}</p>}</div>;
  return <div className="nx-background-list">{tasks.map((task) => <button type="button" key={task.id} className="nx-background-row" onClick={() => shell.showDock("terminal")}><Icon name="terminal" /><span><code>{task.command}</code><small>{t(task.running ? "studio.inProgress" : "studio.done")}{task.exit_code !== null ? ` · ${t("interface.exitCode", { code: task.exit_code })}` : ""}</small></span><Icon name="chevronRight" size={14} /></button>)}</div>;
}

export function ReviewTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const { files, totals, ready } = shell.review;
  if (workspace.artifacts.length === 0 && workspace.computerDiffs.length === 0) return <div className="ag-dock__empty"><Icon name="review" size={28} /><p>{t("dock.noModified")}</p></div>;
  const pending = workspace.artifacts.filter((item) => !workspace.decisions[item.filename]);
  return <div className="ag-review">
    <header className="ag-review__head">
      <strong>{t("dock.review")}</strong>
      <span className="ag-review__sum">{ready ? <><span className="ag-add">+{totals.added}</span> <span className="ag-del">−{totals.removed}</span> · {t("common.files", { count: workspace.artifacts.length })}</> : t("dock.measuring")}</span>
      <span className="ag-spacer" />
      <button type="button" className="button button-quiet" disabled={pending.length === 0} onClick={() => pending.forEach((item) => workspace.reject(item))}>{t("dock.rejectAll")}</button>
      <button type="button" className="button button-primary" disabled={pending.length === 0} onClick={() => { void Promise.all(pending.map((item) => workspace.accept(item))); }}>{t("dock.acceptAll")}</button>
    </header>
    {workspace.computerDiffs.map((diff) => <details className="ag-live-diff" key={`${diff.computerId}/${diff.path}`} open><summary><Icon name="file" size={14} /><code>{diff.path}</code><small>{t("computer.workspaceEdit")}</small></summary><DiffView before={diff.before} after={diff.after} filename={diff.path} /></details>)}
    <ul className="ag-review__list">
      {workspace.artifacts.map((artifact) => {
        const figures = files.find((item) => item.filename === artifact.filename);
        const decision = workspace.decisions[artifact.filename];
        return <li key={artifact.filename} className="ag-review__row">
          <button type="button" className="ag-review__file" title={artifact.filename} onClick={() => { workspace.select(artifact.filename); workspace.setArtifactView("diff"); shell.showDock("files"); }}>
            <FileGlyph kind={classifyArtifact(artifact.filename, artifact.mime_type).kind} />
            <span className="ag-review__name">{artifact.filename}</span>
            {figures?.text && <span className="ag-review__fig">{figures.fresh && <em>{t("stage.new")}</em>}<span className="ag-add">+{figures.added}</span> <span className="ag-del">−{figures.removed}</span></span>}
          </button>
          {decision
            ? <span className={`decision decision--${decision}`}>{decision === "accepted" ? t("stage.accepted") : t("stage.rejected")}</span>
            : <span className="ag-review__actions"><button type="button" className="button button-quiet" onClick={() => workspace.reject(artifact)}>{t("stage.reject")}</button><button type="button" className="button button-primary" onClick={() => void workspace.accept(artifact)}>{t("stage.accept")}</button></span>}
        </li>;
      })}
    </ul>
  </div>;
}

export function FilesTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { artifacts, selected, statuses } = workspace;
  return <div className="ag-files">
    <div className="file-tabs ag-files__tabs" role="tablist" aria-label={t("stage.fileTabs")}>
      {artifacts.length === 0 && <span className="file-tabs__hint">{t("stage.products")}</span>}
      {artifacts.map((file) => <button key={file.filename} role="tab" aria-selected={selected === file.filename} className={`file-tab ${selected === file.filename ? "is-active" : ""}`} onClick={() => { workspace.select(file.filename); workspace.setArtifactView("preview"); }} title={file.filename}>
        <FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} /><span>{file.filename.split("/").pop()}</span>
        {statuses[file.filename] && <i className={`file-tab__badge file-tab__badge--${statuses[file.filename]}`} title={statuses[file.filename] === "added" ? t("stage.new") : t("stage.edited")} />}</button>)}
    </div>
    <div className="ag-files__body"><Workbench /></div>
  </div>;
}

/** An address bar and a page. Only web addresses open; the page runs in a sandboxed frame, and a site that refuses framing is opened in the system browser instead. */
export function BrowserTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [website, setWebsite] = useState(false);
  const [input, setInput] = useState("");
  const [trail, setTrail] = useState<string[]>([]);
  const [at, setAt] = useState(-1);
  const [problem, setProblem] = useState("");
  const [nonce, setNonce] = useState(0);
  const [history, setHistory] = useState<string[]>([]);
  const current = at >= 0 ? trail[at] : null;
  const html = workspace.artifacts.find((file) => file.filename === workspace.selected && isHtmlArtifact(file)) ?? workspace.artifacts.find(isHtmlArtifact);
  useEffect(() => {
    try { const saved: unknown = JSON.parse(localStorage.getItem("nexus_browser_history") ?? "[]"); if (Array.isArray(saved)) setHistory(saved.filter((url): url is string => typeof url === "string" && Boolean(normalizeUrl(url)))); } catch { /* Ignore malformed browser history. */ }
    const clear = () => { setHistory([]); setTrail([]); setAt(-1); setInput(""); };
    window.addEventListener("nexus:clear-browser-history", clear); return () => window.removeEventListener("nexus:clear-browser-history", clear);
  }, []);
  useEffect(() => { setWebsite(false); }, [html?.filename, workspace.runId]);
  useEffect(() => {
    const url = workspace.browserTarget?.url;
    if (!url) return;
    setWebsite(true); setInput(url); setTrail((items) => [...items, url]); setAt((index) => index + 1); rememberBrowserUrl(localStorage, url); setHistory((items) => [url, ...items.filter((item) => item !== url)].slice(0, 100));
  }, [workspace.browserTarget]);
  useEffect(() => {
    const target = workspace.previewTarget;
    if (!target || !workspace.token) return;
    let stopped = false;
    void apiRequest<{ url: string }>(`/api/v1/sandboxes/${target.computerId}/preview`, workspace.token, { method: "POST", body: JSON.stringify({ port: target.port }) }).then((result) => {
      if (stopped) return;
      const url = new URL(result.url, window.location.origin).href;
      setWebsite(true); setInput(url); setTrail([url]); setAt(0); setProblem("");
    }).catch((reason) => { if (!stopped) setProblem(readError(reason)); });
    return () => { stopped = true; };
  }, [workspace.previewTarget, workspace.token]);
  const go = (value: string) => {
    const href = normalizeUrl(value);
    if (!href) { setProblem(t("browser.invalid")); return; }
    if (new URL(href).origin === window.location.origin) { setProblem(t("browser.sameOrigin")); return; } // the app itself must not run inside its own sandbox exception
    setProblem(""); setInput(href);
    rememberBrowserUrl(localStorage, href); setHistory((items) => [href, ...items.filter((item) => item !== href)].slice(0, 100));
    setTrail((items) => [...items.slice(0, at + 1), href]); setAt((index) => index + 1);
  };
  const step = (direction: -1 | 1) => { const next = at + direction; if (next >= 0 && next < trail.length) { setAt(next); setInput(trail[next]); } };
  if (html && !website) return <div className="ag-browser"><HtmlArtifactPreview artifact={html} /><button type="button" className="ag-browser-switch" onClick={() => setWebsite(true)}>{t("result.openWebsite")}</button></div>;
  return <div className="ag-browser">
    <form className="ag-browser__bar" onSubmit={(event) => { event.preventDefault(); go(input); }}>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.back")} disabled={at <= 0} onClick={() => step(-1)}><Icon name="back" size={15} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.forward")} disabled={at >= trail.length - 1} onClick={() => step(1)}><Icon name="forward" size={15} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("browser.reload")} disabled={!current} onClick={() => setNonce((value) => value + 1)}><Icon name="refresh" size={15} /></button>
      <input className="ag-browser__url" value={input} onChange={(event) => setInput(event.target.value)} placeholder={t("browser.placeholder")} aria-label={t("browser.placeholder")} list="nx-browser-history" spellCheck={false} autoFocus={!current} />
      <datalist id="nx-browser-history">{history.map((url) => <option value={url} key={url} />)}</datalist>
      <button type="button" className="ag-iconbtn" aria-label={t("browser.external")} title={t("browser.external")} disabled={!current} onClick={() => { if (current) window.open(current, "_blank", "noopener,noreferrer"); }}><Icon name="external" size={15} /></button>
    </form>
    {problem && <p className="ag-browser__problem" role="alert">{problem}</p>}
    {current
      ? <><iframe key={`${current}-${nonce}`} className="ag-browser__frame" src={current} title={current} sandbox={current.includes("/api/v1/sandboxes/preview/") ? "allow-scripts allow-forms allow-downloads" : "allow-scripts allow-forms allow-same-origin allow-popups"} referrerPolicy="no-referrer" />
        <p className="ag-browser__hint">{t("browser.blankHint")}</p></>
      : <div className="ag-browser__home"><Icon name="globe" size={28} /><p>{t("result.enterWebsite")}</p></div>}
  </div>;
}

export function CanvasTab({ scope, onModal }: { scope: { tenant_id: string; workspace_id: string }; onModal: (kind: "api-key" | "widget") => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { run, runId, workflowId, token } = workspace;
  const shell = useShell();
  const inspectorOpen = shell.inspector;
  const approvals: PendingApproval[] = run.approvals;
  return <div className="ag-canvas">
    <WorkflowStudio embedded toolbarAction={runId && <button type="button" className="button button-quiet ag-canvas__log" aria-pressed={inspectorOpen} onClick={shell.toggleInspector}>{t(inspectorOpen ? "stage.hideLog" : "stage.showLog")}</button>} token={token} scope={scope} activeNodeId={run.active[0]} focusedNodeId={workspace.focusNodeId ?? undefined} approvals={approvals} openWorkflowId={workflowId}
      onApprovalResolved={workspace.dismissApproval} onRun={(next) => workspace.attachRun(next.workflowId, next.runId)} onModal={onModal} />
    {inspectorOpen && runId && <div className="stage-inspector"><LiveInspector token={token} runId={runId} workflowId={workflowId ?? undefined} onClose={shell.toggleInspector} onActiveNode={() => undefined} onApproval={() => undefined} /></div>}
  </div>;
}

/** Conversation-scoped auxiliary pane, with tools grouped into tabs. */
export function RightDock({ width, maxWidth, onResize }: { width: number; maxWidth: number; onResize: (width: number) => void }) {
  const { t } = useLocale();
  const shell = useShell();
  const workspace = useWorkspace();
  const { dock } = shell;
  const [more, setMore] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!more) return;
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setMore(false); };
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") setMore(false); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key); };
  }, [more]);
  const tabs = PRIMARY_TABS.includes(dock.tab) ? PRIMARY_TABS : [...PRIMARY_TABS, dock.tab];
  const label = (tab: DockTab) => t(`interface.tab.${tab}`);
  const choose = (tab: DockTab) => { if (tab === "files" || tab === "browser") workspace.setArtifactView("preview"); shell.showDock(tab); setMore(false); };
  return <aside className={`nx-auxiliary ${dock.expanded ? "is-expanded" : ""}`} aria-label={t("interface.auxiliary")}>
    {!dock.expanded && <PanelResize className="nx-auxiliary-resize" label={t("dock.resize")} value={width} min={320} max={maxWidth} initial={480} reverse onChange={onResize} />}
    <header className="nx-auxiliary-head"><strong>{t("interface.auxiliary")}</strong><span className="ag-spacer" />
      <div ref={root} className="ag-popwrap"><button type="button" className="ag-iconbtn" aria-label={t("interface.openTool")} title={t("interface.openTool")} aria-expanded={more} aria-haspopup="menu" onClick={() => setMore(!more)}><Icon name="more" /></button>
      {more && <div className="ag-popover" role="menu" aria-label={t("interface.openTool")}>{(["files", "browser", "canvas"] as const).map((tab) => <button key={tab} type="button" className="ag-menuitem" role="menuitem" onClick={() => choose(tab)}><Icon name={TAB_ICONS[tab]} />{label(tab)}</button>)}<button type="button" className="ag-menuitem" role="menuitem" onClick={() => { setMore(false); shell.navigate("integrations"); }}><Icon name="extensions" />{t("profile.tools")}</button></div>}</div>
      <button type="button" className="ag-iconbtn" aria-label={t(dock.expanded ? "dock.shrink" : "dock.expand")} title={t(dock.expanded ? "dock.shrink" : "dock.expand")} onClick={shell.expandDock}><Icon name={dock.expanded ? "collapse" : "expand"} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("dock.hide")} title={t("dock.hide")} onClick={shell.closeDock}><Icon name="close" /></button>
    </header>
    <div className="nx-auxiliary-tabs" role="tablist" aria-label={t("interface.auxiliary")} onKeyDown={(event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const at = tabs.indexOf(dock.tab);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (at + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
      choose(tabs[next]); event.currentTarget.querySelector<HTMLButtonElement>(`[data-tab="${tabs[next]}"]`)?.focus();
    }}>{tabs.map((tab) => <button key={tab} id={`nx-tab-${tab}`} data-tab={tab} type="button" role="tab" aria-selected={dock.tab === tab} aria-controls={`nx-pane-${tab}`} tabIndex={dock.tab === tab ? 0 : -1} onClick={() => choose(tab)} title={label(tab)}><Icon name={TAB_ICONS[tab]} size={14} /><span>{label(tab)}</span>{tab === "artifacts" && workspace.artifacts.length > 0 && <small>{workspace.artifacts.length}</small>}{tab === "agents" && workspace.team.agents > 0 && <small>{workspace.team.agents}</small>}</button>)}</div>
    <div className="nx-auxiliary-body" id={`nx-pane-${dock.tab}`} role="tabpanel" aria-labelledby={`nx-tab-${dock.tab}`}>
      {dock.tab === "artifacts" ? <ArtifactDock /> : dock.tab === "agents" ? <AgentsTab /> : dock.tab === "tasks" ? <BackgroundTasksTab /> : dock.tab === "review" ? <ReviewTab /> : dock.tab === "terminal" ? <TerminalPanel docked /> : dock.tab === "browser" ? <BrowserTab /> : <FilesTab />}
    </div>
  </aside>;
}
