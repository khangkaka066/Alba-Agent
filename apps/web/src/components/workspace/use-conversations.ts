"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest } from "@/lib/api";
import { orderTasks } from "@/lib/history.mjs";
import { useWorkspace } from "./workspace-context";

export type RunRow = { id: string; workflow_id: string; status: string; created_at: string; conversation_id: string | null; artifacts: Array<{ filename: string; mime_type: string }> };
export type Conversation = { run: RunRow; name: string };

/** Every task of the workspace, newest first, with the name of the team that ran it. Reloads whenever the open run changes state. */
export function useConversations(): { conversations: Conversation[]; reload: () => Promise<void> } {
  const { t } = useLocale();
  const { token, runId, run } = useWorkspace();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const reload = useCallback(async () => {
    if (!token) return; // wait for the workspace session; the first calls would only be refused
    // Each list is optional: a fresh workspace has no runs yet, and one failing call must not hide the other.
    const [runs, workflows] = await Promise.allSettled([apiRequest<RunRow[]>("/api/v1/runs", token), apiRequest<Array<{ id: string; name: string }>>("/api/v1/workflows", token)]);
    const rows = runs.status === "fulfilled" && Array.isArray(runs.value) ? runs.value : [];
    const names = Object.fromEntries((workflows.status === "fulfilled" && Array.isArray(workflows.value) ? workflows.value : []).map((item) => [item.id, item.name]));
    setConversations(orderTasks(rows, runId).map((row) => ({ run: { ...row, artifacts: Array.isArray(row.artifacts) ? row.artifacts : [] }, name: names[row.workflow_id] ?? t("common.task") })));
  }, [token, t, runId]);
  useEffect(() => { void reload().catch(() => undefined); }, [reload, run.status]);
  return { conversations, reload };
}
