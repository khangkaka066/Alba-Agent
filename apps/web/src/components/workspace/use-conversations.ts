"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest } from "@/lib/api";
import { orderTasks } from "@/lib/history.mjs";
import { useWorkspace } from "./workspace-context";

export type RunRow = { id: string; workflow_id: string | null; status: string; created_at: string; conversation_id: string | null; artifacts: Array<{ filename: string; mime_type: string }> };
export type Conversation = { run: RunRow; name: string };

/** Every task of the workspace, newest first, with the name of the team that ran it. Reloads whenever the open run changes state. */
export function useConversations(): { conversations: Conversation[]; reload: () => Promise<void> } {
  const { t } = useLocale();
  const { token, runId, run, conversationId, messages } = useWorkspace();
  const activeToken = useRef(token);
  activeToken.current = token;
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const reload = useCallback(async () => {
    if (!token) return; // wait for the workspace session; the first calls would only be refused
    // Each list is optional: a fresh workspace has no runs yet, and one failing call must not hide the other.
    const [runs, workflows, threads] = await Promise.allSettled([apiRequest<RunRow[]>("/api/v1/runs", token), apiRequest<Array<{ id: string; name: string }>>("/api/v1/workflows", token), apiRequest<Array<{ id: string; title: string; updated_at: string }>>("/api/v1/conversations", token)]);
    const rows = runs.status === "fulfilled" && Array.isArray(runs.value) ? runs.value : [];
    const names = Object.fromEntries((workflows.status === "fulfilled" && Array.isArray(workflows.value) ? workflows.value : []).map((item) => [item.id, item.name]));
    const threadRows = threads.status === "fulfilled" && Array.isArray(threads.value) ? threads.value : [];
    const linked = new Set(rows.map((row) => row.conversation_id));
    const chats: RunRow[] = threadRows.filter((thread) => !linked.has(thread.id)).map((thread) => ({ id: thread.id, workflow_id: null, status: "chat", created_at: thread.updated_at, conversation_id: thread.id, artifacts: [] }));
    const titles = Object.fromEntries(threadRows.map((thread) => [thread.id, thread.title]));
    if (activeToken.current !== token) return;
    setConversations(orderTasks([...rows, ...chats], runId ?? conversationId).map((row) => ({ run: { ...row, artifacts: Array.isArray(row.artifacts) ? row.artifacts : [] }, name: row.workflow_id ? names[row.workflow_id] ?? t("common.task") : titles[row.id] ?? t("shell.newConversation") })));
  }, [token, t, runId, conversationId]);
  useEffect(() => { setConversations([]); }, [token]);
  useEffect(() => { void reload().catch(() => undefined); }, [reload, run.status, messages.length]);
  useEffect(() => {
    if (!token) return;
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void reload().catch(() => undefined); }, 5000);
    return () => window.clearInterval(timer);
  }, [token, reload]);
  return { conversations, reload };
}
