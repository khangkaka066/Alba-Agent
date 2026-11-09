"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { CanvasTab, RightDock } from "@/components/shell/right-dock";
import { useShell, type NavPage } from "@/components/shell/shell-context";
import { usePanelSize } from "@/components/shell/panel-resize";
import { Composer } from "./composer";
import { StudioHome } from "./studio-home";
import { useWorkspace } from "./workspace-context";

type Props = { scope: { tenant_id: string; workspace_id: string }; onModal: (kind: "api-key" | "widget") => void; onNavigate: (page: NavPage) => void };

/** Conversation first; the existing team canvas remains a separate, mounted workspace. */
export function WorkspaceApp({ scope, onModal, onNavigate }: Props) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const { showDock, closeDock } = shell;
  const { mode, setMode, view, runId } = workspace;
  const [seenCanvas, setSeenCanvas] = useState(mode === "canvas");
  const [width, setWidth] = usePanelSize("nexus_auxiliary_width", 480, 320, 1000);
  const [available, setAvailable] = useState(1200);
  const root = useRef<HTMLDivElement>(null);
  const opened = useRef("");
  const priorRun = useRef(runId);
  const maxWidth = Math.max(320, Math.min(1000, available - 320));
  useEffect(() => {
    if (!root.current) return;
    const observer = new ResizeObserver(([entry]) => setAvailable(entry.contentRect.width));
    observer.observe(root.current); return () => observer.disconnect();
  }, []);
  useEffect(() => { if (width > maxWidth && available > 960) setWidth(maxWidth); }, [width, maxWidth, available, setWidth]);
  useEffect(() => { if (mode === "canvas") setSeenCanvas(true); }, [mode]);
  useEffect(() => { if (mode === "editor") { setMode("mission"); showDock("files"); } }, [mode, setMode, showDock]);
  useEffect(() => { if (view === "canvas") setMode("canvas"); }, [view, setMode]);
  useEffect(() => { if (shell.dock.open && shell.dock.tab === "canvas") setMode("canvas"); }, [shell.dock.open, shell.dock.tab, setMode]);
  useEffect(() => { if (workspace.previewTarget) { showDock("browser"); setMode("mission"); } }, [workspace.previewTarget, showDock, setMode]);
  useEffect(() => { if (workspace.browserTarget) { showDock("browser"); setMode("mission"); } }, [workspace.browserTarget, showDock, setMode]);
  useEffect(() => { if (workspace.plan) showDock("artifacts"); }, [workspace.plan, showDock]);
  useEffect(() => {
    if (priorRun.current && !runId) { closeDock(); opened.current = ""; }
    priorRun.current = runId;
    if (!runId) return;
    const signature = workspace.artifacts.length ? runId : "";
    if (signature && signature !== opened.current) { opened.current = signature; if (!shell.dock.open) showDock("artifacts"); }
  }, [workspace.artifacts, runId, closeDock, showDock, shell.dock.open]);
  useEffect(() => {
    if (!workspace.messages.length && !workspace.plan && !workspace.proposal && !runId) closeDock();
  }, [workspace.messages.length, workspace.plan, workspace.proposal, runId, closeDock]);
  useEffect(() => {
    const toggle = () => setMode(mode === "canvas" ? "mission" : "canvas");
    const artifacts = () => { setMode("mission"); showDock("artifacts"); };
    const diff = () => { setMode("mission"); showDock("review"); };
    const terminal = () => { setMode("mission"); showDock("terminal"); };
    window.addEventListener("nexus:toggle-canvas", toggle); window.addEventListener("nexus:open-artifacts", artifacts); window.addEventListener("nexus:computer-diff", diff); window.addEventListener("nexus:open-terminal", terminal);
    return () => { window.removeEventListener("nexus:toggle-canvas", toggle); window.removeEventListener("nexus:open-artifacts", artifacts); window.removeEventListener("nexus:computer-diff", diff); window.removeEventListener("nexus:open-terminal", terminal); };
  }, [mode, setMode, showDock]);
  const preview = mode !== "canvas" && shell.dock.open && shell.dock.tab !== "canvas";
  const active = workspace.messages.length > 0 || runId !== null || workspace.plan !== null;
  return <div ref={root} className={`nx-workspace ${mode === "canvas" ? "is-canvas" : ""} ${preview ? "has-auxiliary" : ""} ${preview && shell.dock.expanded ? "is-auxiliary-expanded" : ""}`} style={{ "--nx-aux-width": `${Math.min(width, maxWidth)}px` } as React.CSSProperties}>
    <section className="nx-conversation" aria-label={t("stage.chat")} hidden={mode === "canvas"}>{active ? <Composer onNavigate={onNavigate} /> : <StudioHome onOpenSettings={() => onNavigate("settings")} />}</section>
    {preview && <RightDock width={Math.min(width, maxWidth)} maxWidth={maxWidth} onResize={setWidth} />}
    <div className="ag-canvas-stage nx-team-canvas" hidden={mode !== "canvas"}>{seenCanvas && <CanvasTab key={workspace.workflowId ?? "draft"} scope={scope} onModal={onModal} />}</div>
  </div>;
}
