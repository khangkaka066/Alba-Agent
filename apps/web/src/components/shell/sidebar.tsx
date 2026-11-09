"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useLocale } from "@/components/locale-provider";
import { readError } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";
import { ageLabel, statusTone } from "@/lib/history.mjs";
import { groupConversations, loadProjects } from "@/lib/shell.mjs";
import { conversationKey, conversationTime, isUnread, moveSidebarProject, readConversations, sidebarItems, sortSidebarProjects, type SidebarState } from "@/lib/sidebar-view.mjs";
import type { Conversation } from "@/components/workspace/use-conversations";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { ConversationOptions, SidebarPopup, useSidebarPreferences } from "./conversation-options";
import { Icon } from "./icons";
import { NexusLogo } from "@/components/brand/nexus-agent-logo";
import type { NavPage } from "./shell-context";

type Props = { page: NavPage; conversations: Conversation[]; preferenceScope: string; reload: () => Promise<void>; navigate: (page: NavPage) => void; footer: ReactNode };
type RowProps = { item: Conversation; current: boolean; state: SidebarState; onOpen: () => void; onOptions: (anchor: HTMLElement) => void; onDelete: () => void; confirming: boolean; setConfirming: (value: boolean) => void };
function Row({ item, current, state, onOpen, onOptions, onDelete, confirming, setConfirming }: RowProps) {
  const { t } = useLocale();
  const tone = statusTone(item.run.status), unread = isUnread(item, state);
  const timestamp = new Date(conversationTime(item)).toISOString();
  return <li className={`ag-row ${current ? "is-current" : ""} ${unread ? "is-unread" : ""}`}>
    <button type="button" className="ag-row__open" aria-current={current ? "true" : undefined} title={item.name} onClick={onOpen} onContextMenu={event => { event.preventDefault(); onOptions(event.currentTarget); }}>
      {state.showStatus && <span className={`run-dot session-dot run-dot--${tone === "busy" ? "running" : item.run.status}`} aria-hidden="true" />}
      {unread && <span className="nx-sidebar-unread" role="img" aria-label={t("sidebar.filter.unread")} />}
      <span className="ag-row__name">{item.name}</span>
      {state.pinned[conversationKey(item)] && <Icon name="pin" size={11} />}
      {state.showTime && <time className="ag-row__age" dateTime={timestamp}>{ageLabel(timestamp)}</time>}
    </button>
    {confirming ? <span className="ag-row__confirm"><button type="button" onClick={onDelete}>{t("task.deleteYes")}</button><button type="button" onClick={() => setConfirming(false)}>{t("common.cancel")}</button></span>
      : <button type="button" className="ag-row__options" aria-label={t("sidebar.conversationOptions", { name: item.name })} aria-haspopup="menu" onClick={event => onOptions(event.currentTarget)}><Icon name="more" size={14} /></button>}
  </li>;
}

type ItemMenu = { anchor: HTMLElement } & ({ kind: "conversation"; item: Conversation } | { kind: "project"; name: string });
export function Sidebar({ page, conversations, preferenceScope, reload, navigate, footer }: Props) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { state, update, ready } = useSidebarPreferences(preferenceScope);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [asking, setAsking] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [canPickFolder, setCanPickFolder] = useState(false);
  const [projects, setProjects] = useState<Record<string, string>>({});
  const [menu, setMenu] = useState<ItemMenu | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
  useEffect(() => { setCanPickFolder(getDesktop() !== null); }, []);
  useEffect(() => { try { setProjects(loadProjects(window.localStorage)); } catch { setProjects({}); } }, [conversations]);
  useEffect(() => { if (ready && conversations.length && !state.initialized) update(previous => previous.initialized ? previous : readConversations(previous, conversations)); }, [ready, conversations, state.initialized, update]);
  // Opening a conversation, or receiving its next update while it is visible, marks it read.
  useEffect(() => {
    if (!ready || page !== "studio") return;
    const current = conversations.filter(item => item.run.workflow_id ? item.run.id === workspace.runId : item.run.conversation_id === workspace.conversationId);
    if (current.length) update(previous => current.some(item => isUnread(item, previous)) ? readConversations(previous, current) : previous);
  }, [ready, conversations, workspace.runId, workspace.conversationId, page, update]);

  const folderName = workspace.folder?.name;
  const projectNames = JSON.stringify([...new Set([...(folderName ? [folderName] : []), ...groupConversations(conversations, projects).projects.map(group => group.name)])]);
  useEffect(() => {
    if (!ready) return;
    const names: string[] = JSON.parse(projectNames);
    update(previous => { const added = names.filter(name => !previous.projectOrder.includes(name)); return added.length ? { ...previous, projectOrder: [...previous.projectOrder, ...added] } : previous; });
  }, [ready, projectNames, update]);
  const visible = sidebarItems(conversations, state);
  const groups = state.groupBy === "project" ? groupConversations(visible, projects) : { projects: [], loose: visible };
  const includeFolder = state.groupBy === "project" && folderName && !state.archivedOnly && state.filter === "all" && !state.query.trim() && !groups.projects.some(group => group.name === folderName);
  const shown = sortSidebarProjects(includeFolder ? [{ name: folderName, tasks: [] }, ...groups.projects] : groups.projects, state);
  const unreadCount = new Set(conversations.filter(item => isUnread(item, state)).map(conversationKey)).size;

  const open = (item: Conversation) => {
    update(previous => readConversations(previous, [item]));
    if (item.run.workflow_id) { if (item.run.id !== workspace.runId) workspace.openRun(item.run.workflow_id, item.run.id, item.name); }
    else if (item.run.conversation_id && item.run.conversation_id !== workspace.conversationId) workspace.openConversation(item.run.conversation_id);
    navigate("studio");
  };
  const remove = async (item: Conversation) => {
    if (!item.run.conversation_id) return;
    try { await workspace.deleteTask(item.run.conversation_id); setAsking(null); setProblem(""); await reload(); }
    catch (reason) { setProblem(readError(reason)); }
  };
  const row = (item: Conversation) => <Row key={item.run.id} item={item} state={state} current={(item.run.workflow_id ? item.run.id === workspace.runId : item.run.conversation_id === workspace.conversationId) && page === "studio"} onOpen={() => open(item)} onOptions={anchor => setMenu({ kind: "conversation", item, anchor })} onDelete={() => void remove(item)} confirming={asking === item.run.id} setConfirming={value => setAsking(value ? item.run.id : null)} />;
  const start = () => { workspace.newTask(); navigate("studio"); window.setTimeout(() => window.dispatchEvent(new Event("nexus:focus-composer")), 0); };
  const action = (label: string, run: () => void, disabled = false) => <button type="button" role="menuitem" className="nx-sidebar-menu-row" disabled={disabled} onClick={() => { run(); closeMenu(); menu?.anchor.focus(); }}>{label}</button>;
  const toggle = (field: "archived" | "pinned", item: Conversation) => update(previous => { const map = { ...previous[field] }, id = conversationKey(item); if (map[id]) delete map[id]; else map[id] = true; return { ...previous, [field]: map }; });
  const reorder = (name: string, direction: number) => update(previous => ({ ...previous, projectSort: "custom", projectOrder: moveSidebarProject([...shown.map(group => group.name), ...previous.projectOrder.filter(project => !shown.some(group => group.name === project))], name, direction) }));

  return <aside className="ag-sidebar" data-density={state.compact ? "compact" : "comfortable"} aria-label={t("shell.sidebar")}>
    <div className="ag-sidebar__scroll">
      <div className="ag-sidebar-brand"><NexusLogo size={23} /><strong>Alba Agent</strong></div>
      <button type="button" className="ag-newbtn" onClick={start}><Icon name="plus" size={15} /><span>{t("shell.newConversation")}</span></button>
      <section className="ag-section" aria-label={t("shell.projects")}>
        <header className="ag-section__head"><h3>{t("shell.projects")}</h3><span className="ag-section__tools">
          <ConversationOptions state={state} update={update} disabled={!ready} unreadCount={unreadCount} markAllRead={() => update(previous => readConversations(previous, conversations))} />
          {canPickFolder && <button type="button" className="ag-iconbtn ag-iconbtn--small" aria-label={t("repos.add")} title={t("repos.add")} onClick={() => void workspace.openFolder()}><Icon name="folderPlus" size={14} /></button>}
        </span></header>
        {state.groupBy === "project" && shown.length === 0 && !state.archivedOnly && state.filter === "all" && !state.query && <p className="ag-empty">{t(canPickFolder ? "shell.noProjectsDesktop" : "shell.noProjects")}</p>}
        <ul className="ag-list">{shown.map((group, index) => <li key={group.name} className="ag-group">
          <div className="nx-project-heading"><button type="button" className="ag-group__head" aria-expanded={!closed[group.name]} onClick={() => setClosed(value => ({ ...value, [group.name]: !value[group.name] }))}>
            <Icon name="folder" size={15} /><span className="ag-row__name">{group.name}</span><Icon name="chevronRight" size={12} className={closed[group.name] ? "" : "is-open"} />
          </button><button type="button" className="ag-iconbtn ag-iconbtn--small nx-project-options" aria-label={t("sidebar.projectOptions", { name: group.name })} aria-haspopup="menu" disabled={shown.length < 2} onClick={event => setMenu({ kind: "project", name: shown[index].name, anchor: event.currentTarget })}><Icon name="more" size={13} /></button></div>
          {!closed[group.name] && <ul className="ag-list ag-list--nested">{group.tasks.map(row)}{group.tasks.length === 0 && <li className="ag-empty">{t("shell.projectEmpty")}</li>}</ul>}
        </li>)}</ul>
      </section>
      <nav className="ag-nav" aria-label={t("shell.screens")}>
        <button type="button" className={`ag-nav__item ${page === "teammates" ? "is-active" : ""}`} aria-current={page === "teammates" ? "page" : undefined} onClick={() => navigate("teammates")}><Icon name="bolt" size={15} /><span>{t("interface.scheduledTasks")}</span></button>
        <button type="button" className={`ag-nav__item ${page === "integrations" ? "is-active" : ""}`} aria-current={page === "integrations" ? "page" : undefined} onClick={() => navigate("integrations")}><Icon name="customize" size={15} /><span>{t("interface.customizations")}</span></button>
      </nav>
      <section className="ag-section" aria-label={t("shell.conversations")}>
        <header className="ag-section__head"><h3>{t("shell.conversations")}</h3><span className="ag-section__tools"><button type="button" className="ag-iconbtn ag-iconbtn--small" aria-label={t("shell.newConversation")} title={t("shell.newConversation")} onClick={start}><Icon name="plus" size={14} /></button></span></header>
        {visible.length === 0 && <p className="ag-empty">{t(state.archivedOnly ? "sidebar.noArchived" : conversations.length ? "sidebar.noMatches" : "explorer.empty")}</p>}
        {problem && <p className="ag-problem" role="alert">{problem}</p>}
        <ul className="ag-list">{groups.loose.map(row)}</ul>
      </section>
    </div>
    <div className="ag-sidebar__foot">{footer}</div>
    {menu && <SidebarPopup anchor={menu.anchor} onClose={closeMenu} label={t(menu.kind === "project" ? "sidebar.sortProjects" : "sidebar.options")}>
      {menu.kind === "conversation" ? <>
        {action(t(state.pinned[conversationKey(menu.item)] ? "sidebar.unpin" : "sidebar.pin"), () => toggle("pinned", menu.item))}
        {action(t(isUnread(menu.item, state) ? "sidebar.markRead" : "sidebar.markUnread"), () => update(previous => isUnread(menu.item, previous) ? readConversations(previous, [menu.item]) : { ...previous, initialized: true, seen: { ...previous.seen, [conversationKey(menu.item)]: 0 } }))}
        {action(t(state.archived[conversationKey(menu.item)] ? "sidebar.unarchive" : "sidebar.archive"), () => toggle("archived", menu.item))}
        {menu.item.run.conversation_id && <><div role="separator" className="nx-sidebar-menu-separator" />{action(t("task.delete"), () => setAsking(menu.item.run.id))}</>}
      </> : <>
        {action(t("sidebar.moveUp"), () => reorder(menu.name, -1), shown.findIndex(group => group.name === menu.name) <= 0)}
        {action(t("sidebar.moveDown"), () => reorder(menu.name, 1), shown.findIndex(group => group.name === menu.name) === shown.length - 1)}
      </>}
    </SidebarPopup>}
  </aside>;
}
