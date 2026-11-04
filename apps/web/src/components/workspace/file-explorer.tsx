"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest, readError } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";
import { ageLabel, filterTasks, orderTasks, statusTone } from "@/lib/history.mjs";
import { statusLabel } from "@/lib/i18n.mjs";
import { buildTree, classifyArtifact } from "@/lib/workspace.mjs";
import type { TreeNode } from "@/lib/workspace.mjs";
import { FileGlyph } from "./file-glyph";
import { useWorkspace } from "./workspace-context";

type RunRow = { id: string; workflow_id: string; status: string; created_at: string; conversation_id: string | null; artifacts: Array<{ filename: string; mime_type: string }> };

/** A session's icon: a folder. A repository mark joins it once repositories can be connected. */
function sessionIcon() {
  return <svg className="session-icon__glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" /></svg>;
}

function Branch({ nodes, selected, mime, onOpen, depth = 0 }: { nodes: TreeNode[]; selected: string | null; mime: (path: string) => string; onOpen: (path: string) => void; depth?: number }) {
  return <ul className="explorer-list">{nodes.map((node) => node.kind === "dir"
    ? <li key={node.path}><details open><summary style={{ paddingLeft: 8 + depth * 12 }}>{node.name}</summary>
        <Branch nodes={node.children ?? []} selected={selected} mime={mime} onOpen={onOpen} depth={depth + 1} /></details></li>
    : <li key={node.path}>
        <button type="button" aria-current={selected === node.path ? "true" : undefined} className={`explorer-file ${selected === node.path ? "is-selected" : ""}`} style={{ paddingLeft: 8 + depth * 12 }} title={node.path} onClick={() => onOpen(node.path)}>
          <FileGlyph kind={classifyArtifact(node.path, mime(node.path)).kind} /><span>{node.name}</span>{node.status && <i className={`explorer-badge explorer-badge--${node.status}`} />}
        </button></li>)}
  </ul>;
}

/** Every task of the workspace with its status, and the files each produced. Opening a task restores its whole conversation. */
export function FileExplorer({ onOpened }: { onOpened: () => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { token, runId, artifacts, statuses, selected, run } = workspace;
  const [tasks, setTasks] = useState<Array<{ run: RunRow; name: string }>>([]);
  const [asking, setAsking] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [query, setQuery] = useState("");
  const [filtering, setFiltering] = useState(false);
  const [canPickFolder, setCanPickFolder] = useState(false);
  useEffect(() => { setCanPickFolder(getDesktop() !== null); }, []);

  const load = useCallback(async () => {
    if (!token) return; // wait for the workspace session; the first calls would only be refused
    // Each list is optional: a fresh workspace has no runs yet, and one failing call must not hide the other.
    const [runs, workflows] = await Promise.allSettled([apiRequest<RunRow[]>("/api/v1/runs", token), apiRequest<Array<{ id: string; name: string }>>("/api/v1/workflows", token)]);
    const rows = runs.status === "fulfilled" && Array.isArray(runs.value) ? runs.value : [];
    const names = Object.fromEntries((workflows.status === "fulfilled" && Array.isArray(workflows.value) ? workflows.value : []).map((item) => [item.id, item.name]));
    setTasks(orderTasks(rows, runId).map((row) => ({ run: { ...row, artifacts: Array.isArray(row.artifacts) ? row.artifacts : [] }, name: names[row.workflow_id] ?? t("common.task") })));
  }, [token, t, runId]);
  useEffect(() => { void load().catch(() => undefined); }, [load, run.status]);

  const open = (row: RunRow, name: string, path?: string) => {
    if (row.id !== runId) workspace.openRun(row.workflow_id, row.id, name);
    if (path) { workspace.select(path); workspace.setView("workbench"); }
    onOpened();
  };
  const remove = async (row: RunRow) => {
    if (!row.conversation_id) return;
    try { await workspace.deleteTask(row.conversation_id); setAsking(null); setProblem(""); await load(); }
    catch (reason) { setProblem(readError(reason)); }
  };

  const visible = filterTasks(tasks, query);

  const renderTask = ({ run: row, name }: { run: RunRow; name: string }) => {
    const current = row.id === runId;
    const files = current ? artifacts.map((item) => ({ filename: item.filename, mime_type: item.mime_type })) : row.artifacts;
    return <section key={row.id} className={`explorer-task ${current ? "is-current" : ""}`}>
      <div className="explorer-task__head">
        <button type="button" className="explorer-run" title={`${name} · ${statusLabel(t, row.status)}`} aria-current={current ? "true" : undefined} onClick={() => open(row, name)}>
          <span className="session-icon" aria-hidden="true">{sessionIcon()}<i className={`run-dot session-dot run-dot--${statusTone(row.status) === "busy" ? "running" : row.status}`} /></span><span>{name}</span><time className="explorer-age" dateTime={row.created_at}>{ageLabel(row.created_at)}</time></button>
        {row.conversation_id && (asking === row.id
          ? <span className="explorer-confirm"><button type="button" onClick={() => void remove(row)}>{t("task.deleteYes")}</button><button type="button" onClick={() => setAsking(null)}>{t("common.cancel")}</button></span>
          : <button type="button" className="explorer-delete" aria-label={t("task.delete")} title={t("task.delete")} onClick={() => setAsking(row.id)}>×</button>)}
      </div>
      {asking === row.id && <p className="explorer-warning">{t("task.deleteConfirm")}</p>}
      {current && (files.length > 0
        ? <Branch nodes={buildTree(files.map((item) => item.filename), statuses)} selected={selected} mime={(path) => files.find((item) => item.filename === path)?.mime_type ?? ""} onOpen={(path) => open(row, name, path)} />
        : <p className="explorer-nofiles">{t(statusTone(row.status) === "bad" ? "task.noFilesFailed" : "task.noFiles")}</p>)}
    </section>;
  };

  return <nav className="explorer" aria-label={t("explorer.title")}>
    <div className="repo-head">
      <h3 className="explorer-title">{t("sessions.title")}</h3>
      <span className="repo-tools">
        <button type="button" className="header-button" aria-label={t("repos.filter")} title={t("repos.filter")} aria-pressed={filtering} onClick={() => { setFiltering((value) => !value); setQuery(""); }}>
          <svg className="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M7 12h10M10 17h4" /></svg></button>
        {canPickFolder && <button type="button" className="header-button" aria-label={t("repos.add")} title={t("repos.add")} onClick={() => void workspace.openFolder()}>
          <svg className="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></svg></button>}
      </span>
    </div>
    {filtering && <input className="repo-filter" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("repos.filterPlaceholder")} aria-label={t("repos.filter")} />}
    {tasks.length === 0 && <p className="explorer-empty">{t("explorer.empty")}</p>}
    {problem && <p className="explorer-problem" role="alert">{problem}</p>}
    {visible.map(renderTask)}
    {query.trim() && visible.length === 0 && tasks.length > 0 && <p className="explorer-empty">{t("repos.noMatch")}</p>}
  </nav>;
}
