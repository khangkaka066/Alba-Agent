"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocale } from "@/components/locale-provider";
import { conversationTitle } from "@/lib/shell.mjs";
import type { DockTab } from "@/lib/shell.mjs";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { FileGlyph } from "@/components/workspace/file-glyph";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { Icon, type IconName } from "./icons";
import { useShell, type NavPage } from "./shell-context";
import type { ReviewState } from "@/components/workspace/use-review";

/** Closes a popover when the pointer goes elsewhere or Escape is pressed. */
function useDismiss(open: boolean, close: () => void) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) close(); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", escape); };
  }, [open, close]);
  return root;
}

function Menu({ label, icon, children, align = "right", className = "" }: { label: string; icon: IconName; children: (close: () => void) => ReactNode; align?: "left" | "right"; className?: string }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const root = useDismiss(open, close);
  return <div className="ag-popwrap" ref={root}>
    <button type="button" className={`ag-iconbtn ${open ? "is-active" : ""} ${className}`} aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)}><Icon name={icon} size={16} /></button>
    {open && <div className={`ag-popover ag-popover--${align}`} role="menu" aria-label={label}>{children(close)}</div>}
  </div>;
}

function Item({ icon, label, detail, onClick, trailing }: { icon: IconName; label: string; detail?: ReactNode; onClick: () => void; trailing?: ReactNode }) {
  return <button type="button" role="menuitem" className="ag-menuitem" onClick={onClick}><Icon name={icon} size={15} /><span>{label}</span>{detail && <span className="ag-menuitem__detail">{detail}</span>}{trailing}</button>;
}

/** The overview of the right panel: what can be opened, and the files the agent changed. */
function Overview({ review, close }: { review: ReviewState; close: () => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const show = (tab: DockTab) => () => { close(); shell.showDock(tab); };
  const files = workspace.artifacts;
  return <>
    <div className="ag-menu__label">{t("dock.overview")}</div>
    <Item icon="review" label={t("dock.review")} onClick={show("review")} detail={review.ready && files.length > 0 ? <><span className="ag-add">+{review.totals.added}</span> <span className="ag-del">−{review.totals.removed}</span></> : undefined} />
    <Item icon="file" label={t("dock.files")} onClick={show("files")} />
    <Item icon="terminal" label={t("dock.terminal")} onClick={show("terminal")} />
    <Item icon="globe" label={t("dock.browser")} onClick={show("browser")} />
    <Item icon="canvas" label={t("dock.canvas")} onClick={show("canvas")} />
    <Item icon="extensions" label={t("dock.extensions")} trailing={<Icon name="chevronRight" size={12} />} onClick={() => { close(); shell.navigate("integrations"); }} />
    <div className="ag-menu__label">{t("dock.modified")} <span className="ag-count">{files.length}</span></div>
    {files.slice(0, 4).map((file) => <button type="button" key={file.filename} role="menuitem" className="ag-menuitem" onClick={() => { close(); workspace.select(file.filename); shell.showDock("files"); }} title={file.filename}>
      <FileGlyph kind={classifyArtifact(file.filename, file.mime_type).kind} /><span className="ag-menuitem__name">{file.filename.split("/").pop()}</span><span className="ag-menuitem__detail">{file.filename.includes("/") ? file.filename.split("/").slice(0, -1).join("/") : ""}</span></button>)}
    {files.length === 0 && <p className="ag-empty">{t("dock.noModified")}</p>}
    {files.length > 4 && <button type="button" role="menuitem" className="ag-menuitem ag-menuitem--link" onClick={show("review")}>{t("dock.seeAll")}</button>}
  </>;
}

type Props = {
  page: NavPage;
  title: string;
  project: string | null;
  collapsed: boolean;
  onToggleSidebar: () => void;
  review: ReviewState;
  onShortcuts: () => void;
  onNewConversation: () => void;
};

/** The top row: window controls' room, sidebar toggle, history and search, the breadcrumb, and the panel buttons on the right. */
export function TitleBar({ page, title, project, collapsed, onToggleSidebar, review, onShortcuts, onNewConversation }: Props) {
  const { t } = useLocale();
  const shell = useShell();
  const workspace = useWorkspace();
  const heading = page === "studio" ? conversationTitle(title, t("shell.newConversation")) : t(`page.${page}`);
  const copyConversation = async (close: () => void) => {
    close();
    const text = workspace.messages.map((message) => `${message.role === "user" ? t("chat.you") : t("chat.team")}: ${message.text}`).join("\n\n");
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard can be blocked; nothing to undo */ }
  };
  return <header className="ag-titlebar">
    <div className="ag-titlebar__lead">
      <button type="button" className="ag-iconbtn" aria-label={t(collapsed ? "shell.showSidebar" : "shell.hideSidebar")} title={`${t(collapsed ? "shell.showSidebar" : "shell.hideSidebar")} ${shell.hint("toggle-sidebar")}`} aria-expanded={!collapsed} onClick={onToggleSidebar}><Icon name="sidebar" size={16} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.back")} title={t("shell.back")} onClick={() => window.history.back()}><Icon name="back" size={16} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.forward")} title={t("shell.forward")} onClick={() => window.history.forward()}><Icon name="forward" size={16} /></button>
      <button type="button" className="ag-iconbtn" aria-label={t("shell.search")} title={`${t("shell.search")} ${shell.hint("palette")}`} onClick={shell.openPalette}><Icon name="search" size={16} /></button>
    </div>
    <nav className="ag-crumbs" aria-label={t("shell.breadcrumb")}>
      <span className="ag-crumbs__root">{project ?? "NexusAgent"}</span>
      <span className="ag-crumbs__sep" aria-hidden="true">/</span>
      <h1 className="ag-crumbs__title" title={heading}>{heading}</h1>
    </nav>
    <div className="ag-titlebar__tools">
      <Menu label={t("shell.more")} icon="more">{(close) => <>
        <Item icon="plus" label={t("shell.newConversation")} onClick={() => { close(); onNewConversation(); }} />
        <Item icon="copy" label={t("shell.copyConversation")} onClick={() => void copyConversation(close)} />
        <Item icon="log" label={t("shell.runLog")} detail={shell.hint("toggle-inspector")} onClick={() => { close(); shell.toggleInspector(); }} />
        <Item icon="settings" label={t("shell.shortcutsTitle")} onClick={() => { close(); onShortcuts(); }} />
      </>}</Menu>
      <Menu label={t("dock.overview")} icon="review" className={review.ready && review.totals.added + review.totals.removed > 0 ? "has-badge" : ""}>{(close) => <Overview review={review} close={close} />}</Menu>
      <button type="button" className={`ag-iconbtn ${shell.dock.open ? "is-active" : ""}`} aria-label={t(shell.dock.open ? "dock.hide" : "dock.show")} title={`${t(shell.dock.open ? "dock.hide" : "dock.show")} ${shell.hint("toggle-dock")}`} aria-pressed={shell.dock.open} onClick={shell.toggleDock}><Icon name="panelRight" size={16} /></button>
    </div>
  </header>;
}
