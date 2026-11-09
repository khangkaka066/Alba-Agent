"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useLocale } from "@/components/locale-provider";
import { readError } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";
import { ageLabel, filterTasks, statusTone } from "@/lib/history.mjs";
import { groupConversations, loadProjects } from "@/lib/shell.mjs";
import type { Conversation } from "@/components/workspace/use-conversations";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { Icon } from "./icons";
import { NexusLogo } from "@/components/brand/nexus-agent-logo";
import type { NavPage } from "./shell-context";

type Props = { page: NavPage; conversations: Conversation[]; reload: () => Promise<void>; navigate: (page: NavPage) => void; footer: ReactNode };

function Row({ item, current, onOpen, onDelete, confirming, setConfirming }: { item: Conversation; current: boolean; onOpen: () => void; onDelete: () => void; confirming: boolean; setConfirming: (value: boolean) => void }) {
  const { t } = useLocale();
  const tone = statusTone(item.run.status);
  return <li className={`ag-row ${current ? "is-current" : ""}`}>
    <button type="button" className="ag-row__open" aria-current={current ? "true" : undefined} title={item.name} onClick={onOpen}>
      <span className={`run-dot session-dot run-dot--${tone === "busy" ? "running" : item.run.status}`} aria-hidden="true" />
      <span className="ag-row__name">{item.name}</span>
      <time className="ag-row__age" dateTime={item.run.created_at}>{ageLabel(item.run.created_at)}</time>
    </button>
    {item.run.conversation_id && (confirming
      ? <span className="ag-row__confirm"><button type="button" onClick={onDelete}>{t("task.deleteYes")}</button><button type="button" onClick={() => setConfirming(false)}>{t("common.cancel")}</button></span>
      : <button type="button" className="ag-row__delete" aria-label={t("task.delete")} title={t("task.delete")} onClick={() => setConfirming(true)}><Icon name="trash" size={13} /></button>)}
  </li>;
}

/** Left column: start a conversation, the places around it, projects with their conversations, then the profile menu at the foot. */
export function Sidebar({ page, conversations, reload, navigate, footer }: Props) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [query, setQuery] = useState("");
  const [filtering, setFiltering] = useState(false);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [asking, setAsking] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [canPickFolder, setCanPickFolder] = useState(false);
  const [projects, setProjects] = useState<Record<string, string>>({});
  useEffect(() => { setCanPickFolder(getDesktop() !== null); }, []);
  // A task started in an opened folder is remembered under that folder; read again whenever the list changes.
  useEffect(() => { try { setProjects(loadProjects(window.localStorage)); } catch { setProjects({}); } }, [conversations]);

  const visible = filterTasks(conversations, query);
  const groups = groupConversations(visible, projects);
  const folderName = workspace.folder?.name;
  const shown = groups.projects.some((group) => group.name === folderName) || !folderName || query.trim() ? groups.projects : [{ name: folderName, tasks: [] }, ...groups.projects];

  const open = (item: Conversation) => {
    if (item.run.workflow_id) { if (item.run.id !== workspace.runId) workspace.openRun(item.run.workflow_id, item.run.id, item.name); }
    else if (item.run.conversation_id && item.run.conversation_id !== workspace.conversationId) workspace.openConversation(item.run.conversation_id);
    navigate("studio");
  };
  const remove = async (item: Conversation) => {
    if (!item.run.conversation_id) return;
    try { await workspace.deleteTask(item.run.conversation_id); setAsking(null); setProblem(""); await reload(); }
    catch (reason) { setProblem(readError(reason)); }
  };
  const row = (item: Conversation) => <Row key={item.run.id} item={item} current={(item.run.workflow_id ? item.run.id === workspace.runId : item.run.conversation_id === workspace.conversationId) && page === "studio"} onOpen={() => open(item)} onDelete={() => void remove(item)} confirming={asking === item.run.id} setConfirming={(value) => setAsking(value ? item.run.id : null)} />;
  const start = () => { workspace.newTask(); navigate("studio"); window.setTimeout(() => window.dispatchEvent(new Event("nexus:focus-composer")), 0); };

  return <aside className="ag-sidebar" aria-label={t("shell.sidebar")}>
    <div className="ag-sidebar__scroll">
      <div className="ag-sidebar-brand"><NexusLogo size={23} /><strong>Alba Agent</strong></div>
      <button type="button" className="ag-newbtn" onClick={start}><Icon name="plus" size={15} /><span>{t("shell.newConversation")}</span></button>


      <section className="ag-section" aria-label={t("shell.projects")}>
        <header className="ag-section__head">
          <h3>{t("shell.projects")}</h3>
          <span className="ag-section__tools">
            <button type="button" className="ag-iconbtn ag-iconbtn--small" aria-label={t("repos.filter")} title={t("repos.filter")} aria-pressed={filtering} onClick={() => { setFiltering((value) => !value); setQuery(""); }}><Icon name="filter" size={14} /></button>
            {canPickFolder && <button type="button" className="ag-iconbtn ag-iconbtn--small" aria-label={t("repos.add")} title={t("repos.add")} onClick={() => void workspace.openFolder()}><Icon name="folderPlus" size={14} /></button>}
          </span>
        </header>
        {filtering && <input className="ag-filter" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("repos.filterPlaceholder")} aria-label={t("repos.filter")} />}
        {shown.length === 0 && <p className="ag-empty">{t(canPickFolder ? "shell.noProjectsDesktop" : "shell.noProjects")}</p>}
        <ul className="ag-list">
          {shown.map((group) => <li key={group.name} className="ag-group">
            <button type="button" className="ag-group__head" aria-expanded={!closed[group.name]} onClick={() => setClosed((value) => ({ ...value, [group.name]: !value[group.name] }))}>
              <Icon name="folder" size={15} /><span className="ag-row__name">{group.name}</span>
              <Icon name="chevronRight" size={12} className={closed[group.name] ? "" : "is-open"} />
            </button>
            {!closed[group.name] && <ul className="ag-list ag-list--nested">{group.tasks.map(row)}{group.tasks.length === 0 && <li className="ag-empty">{t("shell.projectEmpty")}</li>}</ul>}
          </li>)}
        </ul>
      </section>

      <nav className="ag-nav" aria-label={t("shell.screens")}>
        <button type="button" className={`ag-nav__item ${page === "teammates" ? "is-active" : ""}`} aria-current={page === "teammates" ? "page" : undefined} onClick={() => navigate("teammates")}><Icon name="bolt" size={15} /><span>{t("interface.scheduledTasks")}</span></button>
        <button type="button" className={`ag-nav__item ${page === "integrations" ? "is-active" : ""}`} aria-current={page === "integrations" ? "page" : undefined} onClick={() => navigate("integrations")}><Icon name="customize" size={15} /><span>{t("interface.customizations")}</span></button>
      </nav>

      <section className="ag-section" aria-label={t("shell.conversations")}>
        <header className="ag-section__head">
          <h3>{t("shell.conversations")}</h3>
          <span className="ag-section__tools"><button type="button" className="ag-iconbtn ag-iconbtn--small" aria-label={t("shell.newConversation")} title={t("shell.newConversation")} onClick={start}><Icon name="plus" size={14} /></button></span>
        </header>
        {conversations.length === 0 && <p className="ag-empty">{t("explorer.empty")}</p>}
        {problem && <p className="ag-problem" role="alert">{problem}</p>}
        {query.trim() && visible.length === 0 && conversations.length > 0 && <p className="ag-empty">{t("repos.noMatch")}</p>}
        <ul className="ag-list">{groups.loose.map(row)}</ul>
      </section>
    </div>
    <div className="ag-sidebar__foot">
      {footer}
    </div>
  </aside>;
}
