"use client";

import { useEffect } from "react";
import { useLocale } from "@/components/locale-provider";
import { RightDock } from "@/components/shell/right-dock";
import { useShell, type NavPage } from "@/components/shell/shell-context";
import { Composer } from "./composer";
import { StudioHome } from "./studio-home";
import { useWorkspace } from "./workspace-context";

type Props = { scope: { tenant_id: string; workspace_id: string }; onModal: (kind: "api-key" | "widget") => void; onNavigate: (page: NavPage) => void };

/**
 * One studio, two states. Idle: a single centred prompt. Once a task exists: the conversation in the middle. In both, the right-hand
 * dock (Review, Files, Terminal, Browser, Canvas) opens beside it on demand and follows what the agent produces.
 */
export function WorkspaceApp({ scope, onModal, onNavigate }: Props) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const { view, runId, selected } = workspace;
  const { dock, showDock } = shell;
  const active = workspace.messages.length > 0 || runId !== null;

  // The canvas view (opened from Intelligence, or by the Mod+\ shortcut) lives in the dock; a chosen or freshly produced file opens the Files tab.
  useEffect(() => { if (view === "canvas") showDock("canvas"); }, [view, showDock]);
  useEffect(() => { if (selected) showDock("files"); }, [selected, showDock]);
  useEffect(() => {
    const toggle = () => showDock(dock.open && dock.tab === "canvas" ? "files" : "canvas");
    window.addEventListener("nexus:toggle-canvas", toggle);
    return () => window.removeEventListener("nexus:toggle-canvas", toggle);
  }, [dock.open, dock.tab, showDock]);

  return <div className={`ag-workspace ${dock.open && dock.expanded ? "is-dock-expanded" : ""}`}>
    <section className="ag-center" aria-label={t("stage.chat")}>{active ? <Composer onNavigate={onNavigate} /> : <StudioHome onOpenSettings={() => onNavigate("settings")} />}</section>
    {dock.open && <RightDock scope={scope} onModal={onModal} />}
  </div>;
}
