"use client";

import { useEffect, useState } from "react";
import { WorkflowStudio } from "@/components/canvas/workflow-studio";
import { LiveInspector } from "@/components/inspector/live-inspector";
import type { PendingApproval } from "@/components/teammates/approval-card";
import type { NavPage } from "@/components/studio-app";
import { useLocale } from "@/components/locale-provider";
import { classifyArtifact, isFinished } from "@/lib/workspace.mjs";
import { Composer } from "./composer";
import { FileGlyph } from "./file-glyph";
import { StudioHome } from "./studio-home";
import { TerminalPanel } from "./terminal-panel";
import { Workbench } from "./workbench";
import { useWorkspace } from "./workspace-context";

type Props = { scope: { tenant_id: string; workspace_id: string }; shortcutHint: string; onConnect: () => void; onModal: (kind: "api-key" | "widget") => void; onNavigate: (page: NavPage) => void };

/**
 * One studio, two states. Idle: a single centred prompt. Once a task exists: the conversation on the left and a main
 * stage on the right that shows the deliverables, with the agent canvas one click away.
 */
export function WorkspaceApp({ scope, shortcutHint, onModal, onNavigate }: Props) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { view, setView, run, runId, workflowId, token, artifacts, selected, statuses } = workspace;
  const [canvasSeen, setCanvasSeen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const active = workspace.messages.length > 0 || runId !== null;
  useEffect(() => { if (view === "canvas") setCanvasSeen(true); }, [view]);
  useEffect(() => {
    const toggle = () => { if (active) setView(view === "canvas" ? "workbench" : "canvas"); };
    window.addEventListener("nexus:toggle-canvas", toggle);
    return () => window.removeEventListener("nexus:toggle-canvas", toggle);
  }, [active, view, setView]);
  useEffect(() => { if (!active) setCanvasSeen(false); }, [active]);

  if (!active) return <StudioHome onOpenSettings={() => onNavigate("settings")} />;
  const approvals: PendingApproval[] = run.approvals;
  const working = runId !== null && !isFinished(run.status);
  return <div className="studio-active">
    <aside className="studio-chat" aria-label={t("stage.chat")}><Composer onNavigate={onNavigate} /></aside>
    <section className="studio-stage" aria-label={t("stage.main")}>
      <header className="stage-bar">
        {view === "workbench"
          ? <div className="file-tabs" role="tablist" aria-label={t("stage.fileTabs")}>{artifacts.length === 0 && <span className="file-tabs__hint">{t("stage.products")}</span>}
            {artifacts.map((file) => <button key={file.filename} role="tab" aria-selected={selected === file.filename} className={`file-tab ${selected === file.filename ? "is-active" : ""}`} onClick={() => workspace.select(file.filename)} title={file.filename}>
              <FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} /><span>{file.filename.split("/").pop()}</span>
              {statuses[file.filename] && <i className={`file-tab__badge file-tab__badge--${statuses[file.filename]}`} title={statuses[file.filename] === "added" ? t("stage.new") : t("stage.edited")} />}</button>)}</div>
          : <strong className="stage-bar__title">{t("stage.canvasTitle")}</strong>}
        <span className="stage-bar__spacer" />
        {runId && <span className={`run-chip run-chip--${run.status}`}><span className={`run-dot run-dot--${run.status}`} />{t(`run.stage.${run.status}`) === `run.stage.${run.status}` ? run.status : t(`run.stage.${run.status}`)}</span>}
        {view === "canvas" && runId && <button className="button button-quiet stage-trace" onClick={() => setInspectorOpen((value) => !value)}>{t(inspectorOpen ? "stage.hideLog" : "stage.showLog")}</button>}
        <button className="button button-quiet stage-toggle" onClick={() => setView(view === "canvas" ? "workbench" : "canvas")} title={t("stage.shortcut", { hint: shortcutHint })}>
          {t(view === "canvas" ? "stage.seeProducts" : "stage.seeCanvas")}</button>
      </header>
      <div className="stage-body">
        <div className="stage-pane" hidden={view !== "workbench"}><div className="stage-pane__main"><Workbench /></div>{runId && <TerminalPanel />}</div>
        {(canvasSeen || view === "canvas") && <div className="stage-pane stage-pane--canvas" hidden={view !== "canvas"}>
          <WorkflowStudio embedded token={token} scope={scope} activeNodeId={run.active[0]} approvals={approvals} openWorkflowId={workflowId}
            onApprovalResolved={workspace.dismissApproval} onRun={(next) => workspace.attachRun(next.workflowId, next.runId)} onModal={onModal} />
          {inspectorOpen && runId && <div className="stage-inspector"><LiveInspector token={token} runId={runId} workflowId={workflowId ?? undefined} onClose={() => setInspectorOpen(false)} onActiveNode={() => undefined} onApproval={() => undefined} /></div>}
        </div>}
      </div>
      {working && <span className="stage-progress" aria-hidden="true" />}
    </section>
  </div>;
}
