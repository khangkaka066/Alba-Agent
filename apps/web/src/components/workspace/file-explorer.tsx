"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest, readError } from "@/lib/api";
import { orderTasks, statusTone } from "@/lib/history.mjs";
import { statusLabel } from "@/lib/i18n.mjs";
import { buildTree, classifyArtifact } from "@/lib/workspace.mjs";
import type { TreeNode } from "@/lib/workspace.mjs";
import { FileGlyph } from "./file-glyph";
import { useWorkspace } from "./workspace-context";

type RunRow = { id: string; workflow_id: string; status: string; created_at: string; conversation_id: string | null; artifacts: Array<{ filename: string; mime_type: string }> };

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

  return <nav className="explorer" aria-label={t("explorer.title")}>
    <h3 className="explorer-title">{t("explorer.title")}</h3>
    {tasks.length === 0 && <p className="explorer-empty">{t("explorer.empty")}</p>}
    {problem && <p className="explorer-problem" role="alert">{problem}</p>}
    {tasks.map(({ run: row, name }) => {
      const current = row.id === runId;
      const files = current ? artifacts.map((item) => ({ filename: item.filename, mime_type: item.mime_type })) : row.artifacts;
      return <section key={row.id} className={`explorer-task ${current ? "is-current" : ""}`}>
        <div className="explorer-task__head">
          <button type="button" className="explorer-run" title={`${name} · ${statusLabel(t, row.status)}`} aria-current={current ? "true" : undefined} onClick={() => open(row, name)}>
            <i className={`run-dot run-dot--${statusTone(row.status) === "busy" ? "running" : row.status}`} aria-hidden="true" /><span>{name}</span></button>
          {row.conversation_id && (asking === row.id
            ? <span className="explorer-confirm"><button type="button" onClick={() => void remove(row)}>{t("task.deleteYes")}</button><button type="button" onClick={() => setAsking(null)}>{t("common.cancel")}</button></span>
            : <button type="button" className="explorer-delete" aria-label={t("task.delete")} title={t("task.delete")} onClick={() => setAsking(row.id)}>×</button>)}
        </div>
        {asking === row.id && <p className="explorer-warning">{t("task.deleteConfirm")}</p>}
        {files.length > 0
          ? <Branch nodes={buildTree(files.map((item) => item.filename), current ? statuses : {})} selected={current ? selected : null} mime={(path) => files.find((item) => item.filename === path)?.mime_type ?? ""} onOpen={(path) => open(row, name, path)} />
          : <p className="explorer-nofiles">{t(statusTone(row.status) === "bad" ? "task.noFilesFailed" : "task.noFiles")}</p>}
      </section>;
    })}
  </nav>;
}
