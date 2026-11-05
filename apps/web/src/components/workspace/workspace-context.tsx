"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { useModels } from "@/components/model-context";
import { apiRequest, readError, type JsonRecord } from "@/lib/api";
import { getDesktop, type FolderInfo } from "@/lib/desktop";
import { rememberProject } from "@/lib/shell.mjs";
import { readSse } from "@/lib/sse";
import type { PlanProposal, ProposalAnswers } from "./plan-proposal";
import {
  classifyArtifact, fileStatuses, flattenWorkspaceFiles, initialRunState, isFinished, reduceRunEvent, teamSummary,
  type FileStatus, type RunState, type RuntimeEvent, type TeamSummary,
} from "@/lib/workspace.mjs";

export type Artifact = { filename: string; mime_type: string; size_bytes: number; download_url: string; preview_url: string; created_by_node: string | null };
export type ChatMessage = { id: string; role: "user" | "team" | "note"; text: string; runId?: string; workflowId?: string; attached?: string[] };
/** A deliverable of an earlier task that the next team starts from. */
export type Attachment = { run_id: string; filename: string; run_name: string; size_bytes: number; mime_type: string };
export type View = "workbench" | "canvas";
export type Rigor = "auto" | "minimal" | "standard" | "full_studio";
type Decision = "accepted" | "rejected";
type GenerateResponse = { workflow_spec: JsonRecord; run_id?: string; summary?: string; conversation_id?: string };
export type RunFailure = { failed_node_id: string | null; failed_node_label: string | null; failed_agent_name: string | null; error_type: string; error_message: string; traceback_summary: string; occurred_at: string };
type RunDetail = { status: string; conversation_id: string | null; failure: RunFailure | null };
type Thread = { id: string; messages: Array<{ id: string; role: ChatMessage["role"]; text: string; run_id: string | null; workflow_id: string | null; meta?: { attachments?: Array<{ name: string }> } }> };
const MAX_ATTACHMENTS = 20;
type TaskJob = { task: string; inputFiles: Record<string, string>; rigor: Rigor; options?: { studioId?: string }; sent: Attachment[] };
export type PendingProposal = { card: PlanProposal; job: TaskJob };

type WorkspaceValue = {
  token: string;
  messages: ChatMessage[];
  workflowId: string | null;
  runId: string | null;
  spec: JsonRecord | null;
  conversationId: string | null;
  failure: RunFailure | null;
  attachments: Attachment[];
  addAttachment: (item: Attachment) => void;
  removeAttachment: (item: Attachment) => void;
  team: TeamSummary;
  run: RunState;
  artifacts: Artifact[];
  statuses: Record<string, FileStatus>;
  selected: string | null;
  view: View;
  decisions: Record<string, Decision>;
  folder: FolderInfo | null;
  busy: boolean;
  /** Questions and options waiting for the person's answer before a team is built; null when nothing is asked. */
  proposal: PendingProposal | null;
  /** Build the team with the answers, or with only the stated assumptions when null. */
  answerProposal: (answers: ProposalAnswers | null) => Promise<void>;
  startTask: (prompt: string, rigor: Rigor, options?: { studioId?: string }) => Promise<void>;
  attachRun: (workflowId: string, runId: string) => void;
  openWorkflow: (workflowId: string) => void;
  openRun: (workflowId: string, runId: string, title: string) => void;
  newTask: () => void;
  retry: (mode: "step" | "team") => Promise<void>;
  deleteTask: (conversationId: string) => Promise<void>;
  select: (filename: string | null) => void;
  setView: (view: View) => void;
  openFolder: () => Promise<void>;
  beforeText: (filename: string) => Promise<string | null>;
  fetchArtifact: (artifact: Artifact, as: "text" | "blob") => Promise<string | Blob | null>;
  accept: (artifact: Artifact) => Promise<void>;
  reject: (artifact: Artifact) => void;
  download: (artifact: Artifact) => Promise<void>;
  dismissApproval: (approvalId: string) => void;
};

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}

const WORKSPACE_NOTE = "\n\n[Workspace] The user's project files are in the working directory (workspace_manifest.json maps each name to its real path). Write a changed file under the same name; write new files under the relative path they should live at.";
const PREFERRED_KINDS = ["video", "image", "code", "document", "pdf", "audio", "other"];

function pickDefault(artifacts: Artifact[]): string | null {
  const ranked = [...artifacts].sort((a, b) => PREFERRED_KINDS.indexOf(classifyArtifact(a.filename, a.mime_type).kind) - PREFERRED_KINDS.indexOf(classifyArtifact(b.filename, b.mime_type).kind));
  return ranked[0]?.filename ?? null;
}

export function WorkspaceProvider({ token, children }: { token: string; children: React.ReactNode }) {
  // Callbacks read the language through a ref so changing it never restarts a running stream or rebuilds the handlers.
  const { t } = useLocale();
  const translate = useRef(t);
  translate.current = t;
  const { selected: selectedModel } = useModels();
  const model = useRef(selectedModel);
  model.current = selectedModel;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [spec, setSpec] = useState<JsonRecord | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationRef = useRef<string | null>(null);
  conversationRef.current = conversationId;
  const [failure, setFailure] = useState<RunFailure | null>(null);
  const [streamKey, setStreamKey] = useState(0);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  // Until the person chooses files themselves, a follow-up starts from the files of the task that just finished.
  const chosenByHand = useRef(false);
  const [run, setRun] = useState<RunState>(initialRunState());
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState<View>("workbench");
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [folder, setFolder] = useState<FolderInfo | null>(null);
  const folderName = useRef<string | null>(null);
  folderName.current = folder?.name ?? null;
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<PendingProposal | null>(null);
  const folderMap = useRef<Record<string, string>>({});
  const previous = useRef<Artifact[]>([]);
  const previousToken = useRef("");
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const artifactsRef = useRef<Artifact[]>([]);
  artifactsRef.current = artifacts;

  const note = useCallback((text: string) => {
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "note", text }]);
    const thread = conversationRef.current;
    if (thread) void apiRequest(`/api/v1/conversations/${thread}/messages`, tokenRef.current, { method: "POST", body: JSON.stringify({ text }) }).catch(() => undefined);
  }, []);

  // Desktop: the mounted folder and its changes.
  useEffect(() => {
    const desktop = getDesktop();
    if (!desktop) return;
    void desktop.getFolder().then(setFolder).catch(() => undefined);
    return desktop.onFolderChanged(setFolder);
  }, []);

  const attach = useCallback((nextWorkflow: string, nextRun: string, nextSpec: JsonRecord | null) => {
    previous.current = artifactsRef.current;
    setWorkflowId(nextWorkflow); setRunId(nextRun); setSpec(nextSpec);
    setRun(initialRunState()); setArtifacts([]); setSelected(null); setDecisions({});
  }, []);

  const attachRun = useCallback((nextWorkflow: string, nextRun: string) => {
    attach(nextWorkflow, nextRun, null);
    void apiRequest<JsonRecord>(`/api/v1/workflows/${nextWorkflow}`, token).then(setSpec).catch(() => undefined);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "team", text: translate.current("chat.rerun"), runId: nextRun, workflowId: nextWorkflow }]);
  }, [attach, token]);

  // Reopen an earlier task from the recent list: its files load from the run, its status from the server.
  const openRun = useCallback((nextWorkflow: string, nextRun: string, title: string) => {
    attach(nextWorkflow, nextRun, null);
    setFailure(null); setConversationId(null);
    void apiRequest<JsonRecord>(`/api/v1/workflows/${nextWorkflow}`, token).then(setSpec).catch(() => undefined);
    setMessages([{ id: crypto.randomUUID(), role: "team", text: title, runId: nextRun, workflowId: nextWorkflow }]);
    void apiRequest<RunDetail>(`/api/v1/runs/${nextRun}`, token).then(async (row) => {
      const type = row.status === "completed" ? "RUN_COMPLETED" : row.status === "failed" ? "RUN_FAILED" : null;
      if (type) setRun((current) => reduceRunEvent(current, { id: `history-${nextRun}`, run_id: nextRun, type, node_id: null, occurred_at: "", payload: row.failure ? { message: [row.failure.failed_node_label, row.failure.error_message].filter(Boolean).join(": ") } : {} }));
      setFailure(row.failure);
      if (!row.conversation_id) return;
      const thread = await apiRequest<Thread>(`/api/v1/conversations/${row.conversation_id}`, token);
      setConversationId(thread.id);
      setMessages(thread.messages.map((item) => ({ id: item.id, role: item.role, text: item.text, runId: item.run_id ?? undefined, workflowId: item.workflow_id ?? undefined, attached: item.meta?.attachments?.map((entry) => entry.name) })));
    }).catch(() => undefined);
  }, [attach, token]);

  // Back to the empty, centred prompt.
  const newTask = useCallback(() => {
    previous.current = artifactsRef.current;
    setProposal(null); setMessages([]); setConversationId(null); setFailure(null); setAttachments([]); chosenByHand.current = false; setWorkflowId(null); setRunId(null); setSpec(null); setRun(initialRunState()); setArtifacts([]); setSelected(null); setDecisions({}); setView("workbench");
  }, []);

  // Open a saved workflow on the canvas without starting a run (for example from the Intelligence page).
  const openWorkflow = useCallback((nextWorkflow: string) => {
    previous.current = artifactsRef.current;
    setWorkflowId(nextWorkflow); setRunId(null); setSpec(null); setRun(initialRunState()); setArtifacts([]); setSelected(null); setView("canvas");
    void apiRequest<JsonRecord>(`/api/v1/workflows/${nextWorkflow}`, token).then(setSpec).catch(() => undefined);
  }, [token]);

  const submitTask = useCallback(async (job: TaskJob, extra: JsonRecord) => {
    const response = await apiRequest<GenerateResponse>("/api/v1/architect/generate-workflow", token, {
      method: "POST",
      body: JSON.stringify({ user_requirement_prompt: job.task, auto_run: true, ...(conversationRef.current ? { conversation_id: conversationRef.current } : {}), ...(model.current ? { preferred_model: model.current } : {}), ...(job.options?.studioId ? { studio_id: job.options.studioId } : {}), ...(job.sent.length ? { input_artifacts: job.sent.map((item) => ({ run_id: item.run_id, filename: item.filename })) } : {}), ...(job.rigor === "auto" ? {} : { rigor: job.rigor }), ...(Object.keys(job.inputFiles).length ? { input_files: job.inputFiles } : {}), ...extra }),
    });
    if (!response.run_id) throw new Error(translate.current("workspace.notRun"));
    attach(String(response.workflow_spec.id), response.run_id, response.workflow_spec);
    if (folderName.current) rememberProject(window.localStorage, response.run_id, folderName.current); // lets the sidebar group this task under its project
    setFailure(null);
    setAttachments([]); chosenByHand.current = false; // the files went with this task; the next follow-up starts from its results
    if (response.conversation_id) setConversationId(response.conversation_id);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "team", text: response.summary ?? translate.current("chat.teamBuilt"), runId: response.run_id, workflowId: String(response.workflow_spec.id) }]);
  }, [attach, token]);

  const startTask = useCallback(async (prompt: string, rigor: Rigor, options?: { studioId?: string }) => {
    if (!token) { note(translate.current("workspace.starting")); return; }
    setBusy(true);
    setProposal(null); // a new message replaces any question that is still waiting
    const sent = attachments;
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: prompt, attached: sent.map((item) => item.filename.split("/").pop() ?? item.filename) }]);
    try {
      const desktop = getDesktop();
      let inputFiles: Record<string, string> = {};
      let task = prompt;
      if (desktop && folder) {
        const flat = flattenWorkspaceFiles(await desktop.readTextFiles(900_000));
        inputFiles = flat.files; folderMap.current = flat.map;
        if (Object.keys(flat.files).length) task += WORKSPACE_NOTE;
      } else folderMap.current = {};
      const job: TaskJob = { task, inputFiles, rigor, options, sent };
      // Only the first message of a task is worth interrupting; a follow-up continues work the person already shaped.
      if (rigor === "auto" && !options?.studioId && !conversationRef.current) {
        const card = await apiRequest<PlanProposal>("/api/v1/architect/propose", token, {
          method: "POST",
          body: JSON.stringify({ user_requirement_prompt: task, input_file_names: Object.keys(inputFiles), ...(model.current ? { preferred_model: model.current } : {}) }),
        }).catch(() => null); // asking is a courtesy: if it fails the task is built as asked
        if (card && card.status === "needs_input") { setProposal({ card, job }); return; }
      }
      await submitTask(job, {});
    } catch (error) { note(readError(error)); }
    finally { setBusy(false); }
  }, [attachments, folder, note, submitTask, token]);

  // The person answered the questions (or took the recommendation); build the team with their decisions.
  const answerProposal = useCallback(async (answers: ProposalAnswers | null) => {
    if (!proposal) return;
    setBusy(true);
    try {
      await submitTask(proposal.job, {
        assumptions: proposal.card.assumptions.slice(0, 6),
        ...(answers ? { decisions: answers.decisions.slice(0, 6), ...(answers.level ? { plan_level: answers.level } : {}) } : {}),
      });
      setProposal(null);
    } catch (error) { note(readError(error)); }
    finally { setBusy(false); }
  }, [note, proposal, submitTask]);

  // One SSE stream per run feeds the composer, terminal, progress and the canvas pill.
  useEffect(() => {
    if (!runId || !token) return;
    const controller = new AbortController();
    void fetch(`/api/v1/runs/${runId}/stream`, { headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" }, cache: "no-store", signal: controller.signal })
      .then((response) => readSse(response, (_name, data) => {
        try {
          const event = JSON.parse(data) as RuntimeEvent;
          setRun((current) => reduceRunEvent(current, event));
          const desktop = getDesktop();
          if (event.type === "APPROVAL_REQUIRED") desktop?.notify(translate.current("workspace.notifyApproval"), String(event.payload.action ?? translate.current("workspace.notifyApprovalBody")));
          if (event.type === "RUN_COMPLETED") desktop?.notify(translate.current("workspace.notifyDone"), translate.current("workspace.notifyDoneBody"));
          if (event.type === "RUN_FAILED") desktop?.notify(translate.current("workspace.notifyFailed"), String(event.payload.message ?? translate.current("workspace.notifyFailedBody")));
        } catch { /* Ignore malformed events and keep the stream. */ }
      }, controller.signal))
      .catch(() => undefined);
    return () => controller.abort();
  }, [runId, token, streamKey]);

  // A finished task offers its deliverables to the next one, unless the person has picked files by hand.
  useEffect(() => {
    if (!runId || run.status !== "completed" || artifacts.length === 0 || chosenByHand.current) return;
    const name = typeof spec?.name === "string" ? spec.name : "";
    const offered = artifacts.slice(0, MAX_ATTACHMENTS).map((item) => ({ run_id: runId, filename: item.filename, run_name: name, size_bytes: item.size_bytes, mime_type: item.mime_type }));
    setAttachments((current) => current.length === offered.length && current.every((item, index) => item.run_id === offered[index].run_id && item.filename === offered[index].filename) ? current : offered);
  }, [runId, run.status, artifacts, spec]);
  const addAttachment = useCallback((item: Attachment) => {
    chosenByHand.current = true;
    setAttachments((current) => current.some((entry) => entry.run_id === item.run_id && entry.filename === item.filename) || current.length >= MAX_ATTACHMENTS ? current : [...current, item]);
  }, []);
  const removeAttachment = useCallback((item: Attachment) => {
    chosenByHand.current = true;
    setAttachments((current) => current.filter((entry) => !(entry.run_id === item.run_id && entry.filename === item.filename)));
  }, []);

  // Why a run failed is saved with the run; read it once the run reports failure.
  useEffect(() => {
    if (!runId || !token || run.status !== "failed") return;
    let stopped = false;
    void apiRequest<RunDetail>(`/api/v1/runs/${runId}`, token).then((row) => { if (!stopped) setFailure(row.failure); }).catch(() => undefined);
    return () => { stopped = true; };
  }, [runId, token, run.status]);

  // Deliverables: poll while the run is active, then once more when it ends.
  const finished = isFinished(run.status);
  useEffect(() => {
    if (!runId || !token) return;
    let stopped = false;
    const refresh = async () => {
      try {
        const rows = await apiRequest<Artifact[]>(`/api/v1/runs/${runId}/artifacts`, token);
        if (stopped) return;
        setArtifacts(rows);
        setSelected((current) => current && rows.some((row) => row.filename === current) ? current : pickDefault(rows));
      } catch { /* Files appear once the run produces them. */ }
    };
    void refresh();
    if (finished) return () => { stopped = true; };
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [runId, token, finished]);

  useEffect(() => { if (previousToken.current && previousToken.current !== token) { setWorkflowId(null); setRunId(null); setSpec(null); setArtifacts([]); setRun(initialRunState()); } previousToken.current = token; }, [token]);

  const fetchArtifact = useCallback(async (artifact: Artifact, as: "text" | "blob") => {
    const response = await fetch(artifact.preview_url, { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) return null;
    return as === "text" ? await response.text() : await response.blob();
  }, [token]);

  const beforeText = useCallback(async (filename: string): Promise<string | null> => {
    const desktop = getDesktop();
    const mapped = folderMap.current[filename];
    if (desktop && folder) {
      const local = mapped ?? (folder.files.some((file) => file.path === filename) ? filename : null);
      if (local) return desktop.readFile(local);
    }
    const earlier = previous.current.find((item) => item.filename === filename);
    return earlier ? await fetchArtifact(earlier, "text") as string | null : null;
  }, [fetchArtifact, folder]);

  const statuses = useMemo(() => {
    const current: Record<string, string> = {}; const before: Record<string, string> = {};
    for (const item of artifacts) {
      current[item.filename] = `${item.size_bytes}`;
      const local = folderMap.current[item.filename] ?? item.filename;
      const known = folder?.files.find((file) => file.path === local);
      const earlier = previous.current.find((row) => row.filename === item.filename);
      if (known) before[item.filename] = `local-${known.size}`;
      else if (earlier) before[item.filename] = `${earlier.size_bytes}`;
    }
    const result = fileStatuses(current, before);
    for (const item of artifacts) if (item.filename in before && !(item.filename in result)) result[item.filename] = "modified";
    return result as Record<string, FileStatus>;
  }, [artifacts, folder]);

  const accept = useCallback(async (artifact: Artifact) => {
    const desktop = getDesktop();
    if (desktop && folder) {
      const target = folderMap.current[artifact.filename] ?? artifact.filename;
      const kind = classifyArtifact(artifact.filename, artifact.mime_type);
      const data = await fetchArtifact(artifact, kind.text ? "text" : "blob");
      if (data === null) { note(translate.current("workspace.readFailed", { name: artifact.filename })); return; }
      const result = await desktop.writeFile(target, typeof data === "string" ? data : await data.arrayBuffer());
      if (!result.ok) { note(translate.current("workspace.writeFailed", { name: target, error: String(result.error) })); return; }
      note(translate.current("workspace.saved", { name: target, folder: folder.name }));
    }
    setDecisions((current) => ({ ...current, [artifact.filename]: "accepted" }));
  }, [fetchArtifact, folder, note]);

  const download = useCallback(async (artifact: Artifact) => {
    const data = await fetchArtifact(artifact, "blob");
    if (!(data instanceof Blob)) { note(translate.current("workspace.readFailed", { name: artifact.filename })); return; }
    const link = document.createElement("a"); const url = URL.createObjectURL(data);
    link.href = url; link.download = artifact.filename.split("/").pop() ?? artifact.filename; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [fetchArtifact, note]);
  const reject = useCallback((artifact: Artifact) => setDecisions((current) => ({ ...current, [artifact.filename]: "rejected" })), []);
  const dismissApproval = useCallback((approvalId: string) => setRun((current) => ({ ...current, approvals: current.approvals.filter((item) => item.approval_id !== approvalId) })), []);
  const openFolder = useCallback(async () => { const desktop = getDesktop(); if (desktop) setFolder(await desktop.openFolder() ?? folder); }, [folder]);

  const retry = useCallback(async (mode: "step" | "team") => {
    if (!runId || !workflowId) return;
    try {
      const result = await apiRequest<{ run_id: string; mode: "step" | "team" }>(`/api/v1/runs/${runId}/retry`, token, { method: "POST", body: JSON.stringify({ mode }) });
      setFailure(null);
      if (result.mode === "step") {
        setRun({ ...initialRunState(), status: "running" }); // the same run carries on from its last good step
        setStreamKey((value) => value + 1);
      } else {
        attach(workflowId, result.run_id, spec);
        setMessages((current) => [...current, { id: crypto.randomUUID(), role: "team", text: translate.current("chat.retryTeam"), runId: result.run_id, workflowId }]);
      }
    } catch (error) { note(readError(error)); }
  }, [attach, note, runId, spec, token, workflowId]);

  const deleteTask = useCallback(async (thread: string) => {
    await apiRequest(`/api/v1/conversations/${thread}`, token, { method: "DELETE" });
    if (conversationRef.current === thread) newTask();
  }, [newTask, token]);

  const value: WorkspaceValue = {
    token, messages, workflowId, runId, spec, conversationId, failure, attachments, addAttachment, removeAttachment, team: teamSummary(spec), run, artifacts, statuses, selected, view, decisions, folder, busy, proposal, answerProposal,
    startTask, attachRun, openWorkflow, openRun, newTask, retry, deleteTask, select: setSelected, setView, openFolder, beforeText, fetchArtifact, accept, reject, download, dismissApproval,
  };
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
