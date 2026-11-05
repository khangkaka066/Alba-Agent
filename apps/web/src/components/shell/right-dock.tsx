"use client";

import { useEffect, useRef, useState } from "react";
import { WorkflowStudio } from "@/components/canvas/workflow-studio";
import { LiveInspector } from "@/components/inspector/live-inspector";
import type { PendingApproval } from "@/components/teammates/approval-card";
import { useLocale } from "@/components/locale-provider";
import { FileGlyph } from "@/components/workspace/file-glyph";
import { TerminalPanel } from "@/components/workspace/terminal-panel";
import { Workbench } from "@/components/workspace/workbench";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { DOCK_TABS, normalizeUrl, type DockTab } from "@/lib/shell.mjs";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { Icon, type IconName } from "./icons";
import { useShell } from "./shell-context";

const TAB_ICONS: Record<DockTab, IconName> = { review: "review", files: "file", terminal: "terminal", browser: "globe", canvas: "canvas" };
const WIDTH_KEY = "nexus_dock_width";
const MIN_WIDTH = 360;

function ReviewTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const { files, totals, ready } = shell.review;
  if (workspace.artifacts.length === 0) return <div className="ag-dock__empty"><Icon name="review" size={28} /><p>{t("dock.noModified")}</p></div>;
  const pending = workspace.artifacts.filter((item) => !workspace.decisions[item.filename]);
  return <div className="ag-review">
    <header className="ag-review__head">
      <strong>{t("dock.review")}</strong>
      <span className="ag-review__sum">{ready ? <><span className="ag-add">+{totals.added}</span> <span className="ag-del">−{totals.removed}</span> · {t("common.files", { count: workspace.artifacts.length })}</> : t("dock.measuring")}</span>
      <span className="ag-spacer" />
      <button type="button" className="button button-quiet" disabled={pending.length === 0} onClick={() => pending.forEach((item) => workspace.reject(item))}>{t("dock.rejectAll")}</button>
      <button type="button" className="button button-primary" disabled={pending.length === 0} onClick={() => { void Promise.all(pending.map((item) => workspace.accept(item))); }}>{t("dock.acceptAll")}</button>
    </header>
    <ul className="ag-review__list">
      {workspace.artifacts.map((artifact) => {
        const figures = files.find((item) => item.filename === artifact.filename);
        const decision = workspace.decisions[artifact.filename];
        return <li key={artifact.filename} className="ag-review__row">
          <button type="button" className="ag-review__file" title={artifact.filename} onClick={() => { workspace.select(artifact.filename); shell.showDock("files"); }}>
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

function FilesTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { artifacts, selected, statuses } = workspace;
  return <div className="ag-files">
    <div className="file-tabs ag-files__tabs" role="tablist" aria-label={t("stage.fileTabs")}>
      {artifacts.length === 0 && <span className="file-tabs__hint">{t("stage.products")}</span>}
      {artifacts.map((file) => <button key={file.filename} role="tab" aria-selected={selected === file.filename} className={`file-tab ${selected === file.filename ? "is-active" : ""}`} onClick={() => workspace.select(file.filename)} title={file.filename}>
        <FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} /><span>{file.filename.split("/").pop()}</span>
        {statuses[file.filename] && <i className={`file-tab__badge file-tab__badge--${statuses[file.filename]}`} title={statuses[file.filename] === "added" ? t("stage.new") : t("stage.edited")} />}</button>)}
    </div>
    <div className="ag-files__body"><Workbench /></div>
  </div>;
}

/** An address bar and a page. Only web addresses open; the page runs in a sandboxed frame, and a site that refuses framing is opened in the system browser instead. */
function BrowserTab() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const [input, setInput] = useState("");
  const [trail, setTrail] = useState<string[]>([]);
  const [at, setAt] = useState(-1);
  const [problem, setProblem] = useState("");
  const [nonce, setNonce] = useState(0);
  const current = at >= 0 ? trail[at] : null;
  const go = (value: string) => {
    const href = normalizeUrl(value);
    if (!href) { setProblem(t("browser.invalid")); return; }
    if (new URL(href).origin === window.location.origin) { setProblem(t("browser.sameOrigin")); return; } // the app itself must not run inside its own sandbox exception
    setProblem(""); setInput(href);
    setTrail((items) => [...items.slice(0, at + 1), href]); setAt((index) => index + 1);
  };
  const step = (direction: -1 | 1) => { const next = at + direction; if (next >= 0 && next < trail.length) { setAt(next); setInput(trail[next]); } };
  const files = workspace.artifacts;
  return <div className="ag-browser">
    <form className="ag-browser__bar" onSubmit={(event) => { event.preventDefault(); go(input); }}>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.back")} disabled={at <= 0} onClick={() => step(-1)}><Icon name="back" size={15} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.forward")} disabled={at >= trail.length - 1} onClick={() => step(1)}><Icon name="forward" size={15} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("browser.reload")} disabled={!current} onClick={() => setNonce((value) => value + 1)}><Icon name="refresh" size={15} /></button>
      <input className="ag-browser__url" value={input} onChange={(event) => setInput(event.target.value)} placeholder={t("browser.placeholder")} aria-label={t("browser.placeholder")} spellCheck={false} autoFocus={!current} />
      <button type="button" className="ag-iconbtn" aria-label={t("browser.external")} title={t("browser.external")} disabled={!current} onClick={() => { if (current) window.open(current, "_blank", "noopener,noreferrer"); }}><Icon name="external" size={15} /></button>
    </form>
    {problem && <p className="ag-browser__problem" role="alert">{problem}</p>}
    {current
      ? <><iframe key={`${current}-${nonce}`} className="ag-browser__frame" src={current} title={current} sandbox="allow-scripts allow-forms allow-same-origin allow-popups" referrerPolicy="no-referrer" />
        <p className="ag-browser__hint">{t("browser.blankHint")}</p></>
      : <div className="ag-browser__home">
        <ul className="ag-launch">
          <li><button type="button" onClick={() => shell.showDock("review")}><Icon name="review" size={16} />{t("dock.review")}</button></li>
          <li><button type="button" onClick={() => shell.showDock("files")}><Icon name="file" size={16} />{t("dock.openFile")}</button></li>
          <li><button type="button" onClick={() => shell.showDock("terminal")}><Icon name="terminal" size={16} />{t("dock.terminal")}</button></li>
          <li><button type="button" onClick={() => shell.showDock("canvas")}><Icon name="canvas" size={16} />{t("dock.canvas")}</button></li>
        </ul>
        <div className="ag-menu__label">{t("dock.modified")} <span className="ag-count">{files.length}</span></div>
        {files.length === 0 && <p className="ag-empty">{t("dock.noModified")}</p>}
        <ul className="ag-launch ag-launch--files">{files.slice(0, 6).map((file) => <li key={file.filename}><button type="button" title={file.filename} onClick={() => { workspace.select(file.filename); shell.showDock("files"); }}><FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} />{file.filename.split("/").pop()}<small>{file.filename.includes("/") ? file.filename.split("/").slice(0, -1).join("/") : ""}</small></button></li>)}</ul>
      </div>}
  </div>;
}

function CanvasTab({ scope, onModal }: { scope: { tenant_id: string; workspace_id: string }; onModal: (kind: "api-key" | "widget") => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { run, runId, workflowId, token } = workspace;
  const shell = useShell();
  const inspectorOpen = shell.inspector;
  const approvals: PendingApproval[] = run.approvals;
  return <div className="ag-canvas">
    {runId && <button type="button" className="button button-quiet ag-canvas__log" onClick={shell.toggleInspector}>{t(inspectorOpen ? "stage.hideLog" : "stage.showLog")}</button>}
    <WorkflowStudio embedded token={token} scope={scope} activeNodeId={run.active[0]} approvals={approvals} openWorkflowId={workflowId}
      onApprovalResolved={workspace.dismissApproval} onRun={(next) => workspace.attachRun(next.workflowId, next.runId)} onModal={onModal} />
    {inspectorOpen && runId && <div className="stage-inspector"><LiveInspector token={token} runId={runId} workflowId={workflowId ?? undefined} onClose={shell.toggleInspector} onActiveNode={() => undefined} onApproval={() => undefined} /></div>}
  </div>;
}

/** The right-hand panel: Review, Files, Terminal, Browser and the agent canvas, resizable and expandable. */
export function RightDock({ scope, onModal }: { scope: { tenant_id: string; workspace_id: string }; onModal: (kind: "api-key" | "widget") => void }) {
  const { t } = useLocale();
  const shell = useShell();
  const { dock } = shell;
  const [width, setWidth] = useState(560);
  const [seen, setSeen] = useState<Record<string, boolean>>({});
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);
  useEffect(() => { try { const saved = Number(window.localStorage.getItem(WIDTH_KEY)); if (saved >= MIN_WIDTH) setWidth(saved); } catch { /* the default width applies */ } }, []);
  useEffect(() => { setSeen((value) => value[dock.tab] ? value : { ...value, [dock.tab]: true }); }, [dock.tab]);

  const onDown = (event: React.PointerEvent<HTMLDivElement>) => { drag.current = { startX: event.clientX, startWidth: width }; event.currentTarget.setPointerCapture(event.pointerId); };
  const onMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const max = Math.max(MIN_WIDTH, Math.floor(window.innerWidth * 0.75));
    setWidth(Math.min(max, Math.max(MIN_WIDTH, drag.current.startWidth + (drag.current.startX - event.clientX))));
  };
  const onUp = () => { if (!drag.current) return; drag.current = null; try { window.localStorage.setItem(WIDTH_KEY, String(width)); } catch { /* not saved */ } };
  const resizeKey = (event: React.KeyboardEvent) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setWidth((value) => Math.max(MIN_WIDTH, value + (event.key === "ArrowLeft" ? 24 : -24))); } };

  return <aside className={`ag-dock ${dock.expanded ? "is-expanded" : ""}`} style={dock.expanded ? undefined : { width }} aria-label={t("dock.title")}>
    {!dock.expanded && <div className="ag-dock__grip" role="separator" aria-orientation="vertical" aria-label={t("dock.resize")} tabIndex={0} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onKeyDown={resizeKey} />}
    <header className="ag-dock__bar">
      <div className="ag-tabs" role="tablist" aria-label={t("dock.title")}>
        {DOCK_TABS.map((tab) => <button key={tab} type="button" role="tab" aria-selected={dock.tab === tab} className={`ag-tab ${dock.tab === tab ? "is-active" : ""}`} onClick={() => shell.showDock(tab)}><Icon name={TAB_ICONS[tab]} size={14} /><span>{t(`dock.${tab}`)}</span>
          {tab === "review" && shell.review.ready && shell.review.totals.added + shell.review.totals.removed > 0 && <small className="ag-tab__fig"><span className="ag-add">+{shell.review.totals.added}</span><span className="ag-del">−{shell.review.totals.removed}</span></small>}</button>)}
      </div>
      <span className="ag-spacer" />
      <button type="button" className="ag-iconbtn" aria-label={t(dock.expanded ? "dock.shrink" : "dock.expand")} title={t(dock.expanded ? "dock.shrink" : "dock.expand")} onClick={shell.expandDock}><Icon name={dock.expanded ? "collapse" : "expand"} size={15} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("dock.hide")} title={`${t("dock.hide")} ${shell.hint("toggle-dock")}`} onClick={shell.closeDock}><Icon name="close" size={15} /></button>
    </header>
    <div className="ag-dock__body">
      <div className="ag-dock__pane" hidden={dock.tab !== "review"}>{seen.review && <ReviewTab />}</div>
      <div className="ag-dock__pane" hidden={dock.tab !== "files"}><FilesTab /></div>
      <div className="ag-dock__pane" hidden={dock.tab !== "terminal"}>{seen.terminal && <TerminalPanel docked />}</div>
      <div className="ag-dock__pane" hidden={dock.tab !== "browser"}>{seen.browser && <BrowserTab />}</div>
      <div className="ag-dock__pane" hidden={dock.tab !== "canvas"}>{seen.canvas && <CanvasTab scope={scope} onModal={onModal} />}</div>
    </div>
  </aside>;
}
