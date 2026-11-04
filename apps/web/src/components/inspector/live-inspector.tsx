"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { apiRequest, readError } from "@/lib/api";
import { readSse } from "@/lib/sse";
import type { PendingApproval } from "@/components/teammates/approval-card";
import { RunArtifactGallery } from "./run-artifact-gallery";

type RuntimeEvent = { id: string; run_id: string; type: string; node_id: string | null; occurred_at: string; payload: Record<string, unknown> };
type Usage = { totals?: { prompt_tokens?: number; completion_tokens?: number; total_cost_usd?: string; sandbox_compute_seconds?: string; average_latency_ms?: number } };
type Checkpoint = { id: string; sequence: number; state: Record<string, unknown>; created_at: string };
type Props = { token: string; runId?: string; workflowId?: string; onClose: () => void; onActiveNode: (node: string | undefined) => void; onApproval: (approval: PendingApproval) => void };

function eventLabel(event: RuntimeEvent): string {
  const p = event.payload;
  if (event.type === "FLOW_STATE_CHANGED") return `${String(p.status ?? "Updated")} · ${String(p.node_id ?? event.node_id ?? "workflow")}`;
  if (event.type === "CREW_AGENT_THOUGHT") return String(p.content ?? p.thought ?? p.message ?? "Team shared an update");
  if (event.type === "NEXUSGEN_CODE_GENERATED") return String(p.code ?? p.content ?? "Code prepared");
  if (event.type === "SANDBOX_TERMINAL_OUTPUT") return String(p.content ?? p.output ?? "");
  if (event.type === "TOOL_INVOKED") return `Tool · ${String(p.tool ?? p.name ?? "action")}`;
  if (event.type === "APPROVAL_REQUIRED" && p.kind === "consensus_arbitration") return `Consensus review · ${Number(p.consensus_confidence ?? 0).toFixed(2)} confidence · ${String(p.dissent_report ?? "Model drafts disagree")}`;
  if (event.type === "APPROVAL_REQUIRED") return `Approval requested · ${String(p.action ?? "Review action")}`;
  if (event.type === "APPROVAL_RESOLVED") return `Approval ${String(p.decision ?? "resolved")}`;
  if (event.type === "RUN_COMPLETED") return "Workflow completed";
  if (event.type === "RUN_FAILED") return `Workflow failed · ${String(p.message ?? p.error_type ?? "runtime error")}`;
  return event.type.replaceAll("_", " ").toLowerCase();
}

function eventTitle(type: string): string {
  if (type === "NEXUSGEN_CODE_GENERATED") return "CODE GENERATED";
  if (type === "CREW_AGENT_THOUGHT") return "TEAM UPDATE";
  return type.replaceAll("_", " ");
}

export function LiveInspector({ token, runId, workflowId, onClose, onActiveNode, onApproval }: Props) {
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [connection, setConnection] = useState("Waiting for a run");
  const [usage, setUsage] = useState<Usage | null>(null);
  const [sandboxId, setSandboxId] = useState("");
  const [frame, setFrame] = useState("");
  const [screenStatus, setScreenStatus] = useState("Connect a computer to view live frames");
  const [terminalCommand, setTerminalCommand] = useState("");
  const [terminalOutput, setTerminalOutput] = useState("");
  const [tab, setTab] = useState<"trace" | "computer">("trace");
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [checkpointId, setCheckpointId] = useState("");
  const [stateEdit, setStateEdit] = useState('{"input_data":{}}');
  const [replayPrompt, setReplayPrompt] = useState("");
  const [replayModel, setReplayModel] = useState("");
  const [forkStatus, setForkStatus] = useState("");
  const [forkRuns, setForkRuns] = useState<{ a: string; b: string } | null>(null);

  useEffect(() => {
    const showTimeline = () => {
      setTab("trace");
      document.querySelector(".time-travel-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    window.addEventListener("nexus:open-timeline", showTimeline);
    return () => window.removeEventListener("nexus:open-timeline", showTimeline);
  }, []);

  useEffect(() => {
    if (!runId || !token) return;
    let stopped = false;
    void apiRequest<Checkpoint[]>(`/api/v1/runs/${runId}/checkpoints`, token).then((rows) => {
      if (stopped) return;
      setCheckpoints(rows);
      if (rows.length) { const latest = rows[rows.length - 1]; setCheckpointId(latest.id); setStateEdit(JSON.stringify({ input_data: latest.state.input_data ?? {}, node_outputs: latest.state.node_outputs ?? {} }, null, 2)); }
    }).catch(() => { if (!stopped) setCheckpoints([]); });
    return () => { stopped = true; };
  }, [runId, token, events.length]);

  const replayFromHere = async () => {
    if (!runId || !checkpointId) return;
    try {
      const edited = JSON.parse(stateEdit) as Record<string, unknown>;
      const result = await apiRequest<{ run_id: string }>(`/api/v1/runs/${runId}/checkpoints/${checkpointId}/rewind`, token, { method: "POST", body: JSON.stringify({ mutated_state: edited, node_overrides: replayPrompt || replayModel ? { ...(replayPrompt ? { prompt: replayPrompt } : {}), ...(replayModel ? { model: replayModel } : {}) } : {} }) });
      setForkStatus(`Replay queued · ${result.run_id.slice(0, 8)}`);
    } catch (error) { setForkStatus(readError(error)); }
  };
  const forkComparison = async () => {
    if (!runId || !checkpointId) return;
    try {
      const result = await apiRequest<{ branch_a: { run_id: string }; branch_b: { run_id: string } }>(`/api/v1/runs/${runId}/checkpoints/${checkpointId}/fork`, token, { method: "POST", body: JSON.stringify({ branch_a: { ...(replayPrompt ? { prompt: replayPrompt } : {}), ...(replayModel ? { model: replayModel } : {}) }, branch_b: { ...(replayPrompt ? { prompt: `${replayPrompt}\nReturn a concise alternative and state uncertainty.` } : {}), model: "openai/gpt-4.1-mini" } }) });
      setForkRuns({ a: result.branch_a.run_id, b: result.branch_b.run_id });
      setForkStatus(`A ${result.branch_a.run_id.slice(0, 8)} · B ${result.branch_b.run_id.slice(0, 8)} queued`);
    } catch (error) { setForkStatus(readError(error)); }
  };
  const compareForks = async () => {
    if (!forkRuns) return;
    try {
      const result = await apiRequest<{ output_diff: string; latency_delta_ms: number; cost_delta_usd: number; validation_status: string }>("/api/v1/runs/compare", token, { method: "POST", body: JSON.stringify({ branch_a_run_id: forkRuns.a, branch_b_run_id: forkRuns.b }) });
      setForkStatus(`Comparison ${result.validation_status} · latency Δ ${result.latency_delta_ms}ms · cost Δ $${result.cost_delta_usd.toFixed(4)}\n${result.output_diff}`);
    } catch (error) { setForkStatus(readError(error)); }
  };

  useEffect(() => {
    if (!runId || !token) return;
    const controller = new AbortController();
    setEvents([]); setConnection("Connecting to live run…");
    void fetch(`/api/v1/runs/${runId}/stream`, { headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" }, cache: "no-store", signal: controller.signal })
      .then((response) => readSse(response, (_type, data) => {
        try {
          const event = JSON.parse(data) as RuntimeEvent;
          setEvents((current) => [...current.slice(-199), event]);
          if (event.type === "FLOW_STATE_CHANGED") onActiveNode(event.payload.status === "running" ? String(event.payload.node_id ?? event.node_id ?? "") || undefined : undefined);
          if (event.type === "RUN_COMPLETED" || event.type === "RUN_FAILED") { onActiveNode(undefined); setConnection(event.type === "RUN_COMPLETED" ? "Run completed" : `Run failed${typeof event.payload.message === "string" ? ` · ${event.payload.message}` : ""}`); }
          if (event.type === "APPROVAL_REQUIRED" && typeof event.payload.approval_id === "string") onApproval({ approval_id: event.payload.approval_id, run_id: event.run_id, node_id: event.node_id ?? undefined, action: String(event.payload.action ?? (event.payload.kind === "consensus_arbitration" ? "Arbitrate conflicting model outputs" : "Approval required")), rationale: String(event.payload.dissent_report ?? event.payload.rationale ?? "Review the requested action."), required_role: String(event.payload.required_role ?? "builder"), routine_run_id: typeof event.payload.routine_run_id === "string" ? event.payload.routine_run_id : undefined });
          if (event.type !== "RUN_COMPLETED" && event.type !== "RUN_FAILED") setConnection("Live · receiving events");
        } catch { /* Ignore malformed events and preserve the active stream. */ }
      }, controller.signal))
      .catch((error: unknown) => { if (!controller.signal.aborted) setConnection(readError(error)); });
    return () => controller.abort();
  }, [runId, token, onActiveNode, onApproval]);

  useEffect(() => {
    if (!token || !workflowId) return;
    let stopped = false;
    const refresh = async () => {
      try { const result = await apiRequest<Usage>(`/api/v1/analytics/usage?days=365&workflow_id=${workflowId}${runId ? `&run_id=${runId}` : ""}`, token); if (!stopped) setUsage(result); }
      catch { /* Usage remains available when analytics permissions allow it. */ }
    };
    void refresh(); const timer = window.setInterval(() => void refresh(), 15000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [workflowId, runId, token]);

  useEffect(() => {
    if (!sandboxId || !token || tab !== "computer") return;
    const controller = new AbortController(); setScreenStatus("Connecting to the computer…");
    void fetch(`/api/v1/sandboxes/${sandboxId}/screen`, { headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" }, cache: "no-store", signal: controller.signal }).then((response) => {
      if (!response.ok || !response.body) throw new Error(`Computer stream unavailable (${response.status})`);
      setScreenStatus("Connected · live frames");
      return readSse(response, (eventType, data) => {
        if (eventType !== "screen_frame") return;
        try { const parsed = JSON.parse(data) as { png_base64?: string }; if (parsed.png_base64) setFrame(`data:image/png;base64,${parsed.png_base64}`); }
        catch { setScreenStatus("Received an invalid screen frame"); }
      }, controller.signal);
    }).catch((error: unknown) => { if (!controller.signal.aborted) setScreenStatus(readError(error)); });
    return () => controller.abort();
  }, [sandboxId, token, tab]);

  const totals = usage?.totals;
  const runTerminal = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sandboxId || !terminalCommand.trim()) return;
    const controller = new AbortController();
    setTerminalOutput("");
    try {
      const response = await fetch(`/api/v1/sandboxes/${sandboxId}/terminal/stream`, {
        method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify({ command: terminalCommand, timeout_seconds: 60 }), signal: controller.signal,
      });
      await readSse(response, (event, data) => {
        try { const payload = JSON.parse(data) as { text?: string; exit_code?: number; error?: string; approval_id?: string; action?: string; required_role?: string }; if (event === "stdout" || event === "stderr") setTerminalOutput((current) => current + (payload.text ?? "")); if (event === "result") setTerminalOutput((current) => `${current}\n[exit ${payload.exit_code ?? "?"}]`); if (event === "error") setTerminalOutput((current) => `${current}\n${payload.error ?? "Command failed"}`); if (event === "approval_required" && payload.approval_id) { setTerminalOutput((current) => `${current}\n[approval required]`); onApproval({ approval_id: payload.approval_id, run_id: runId, action: payload.action ?? terminalCommand, required_role: payload.required_role ?? "admin" }); } }
        catch { setTerminalOutput((current) => `${current}\nInvalid terminal event`); }
      }, controller.signal);
    } catch (error) { setTerminalOutput(readError(error)); }
  };
  return <aside className="inspector-drawer"><header className="inspector-head"><div><span className="eyebrow">RUN INSPECTOR</span><h2>{runId ? `Run ${runId.slice(0, 8)}` : "Live execution"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close inspector">×</button></header><div className="inspector-state"><span className={connection.includes("failed") || connection.includes("unavailable") ? "state-dot state-dot--error" : "state-dot"} />{connection}</div><div className="usage-cards"><div><span>Tokens</span><strong>{((totals?.prompt_tokens ?? 0) + (totals?.completion_tokens ?? 0)).toLocaleString()}</strong><small>{(totals?.prompt_tokens ?? 0).toLocaleString()} in · {(totals?.completion_tokens ?? 0).toLocaleString()} out</small></div><div><span>Spend</span><strong>${Number(totals?.total_cost_usd ?? 0).toFixed(4)}</strong><small>Run total to date</small></div><div><span>Computer time</span><strong>{Number(totals?.sandbox_compute_seconds ?? 0).toFixed(1)}s</strong><small>{Number(totals?.average_latency_ms ?? 0).toFixed(0)}ms avg latency</small></div></div><div className="inspector-tabs"><button className={tab === "trace" ? "selected" : ""} onClick={() => setTab("trace")}>Execution trace <span>{events.length}</span></button><button className={tab === "computer" ? "selected" : ""} onClick={() => setTab("computer")}>Computer view</button></div>
    {runId && <RunArtifactGallery runId={runId} token={token} />}
    {tab === "trace" ? <><section className="time-travel-panel"><div className="trace-event__meta"><strong>TIME-TRAVEL &amp; FORK</strong><span>{checkpoints.length} snapshots</span></div><label className="field"><span>Replay from checkpoint</span><select value={checkpointId} onChange={(event) => { setCheckpointId(event.target.value); const selected = checkpoints.find((row) => row.id === event.target.value); if (selected) setStateEdit(JSON.stringify({ input_data: selected.state.input_data ?? {}, node_outputs: selected.state.node_outputs ?? {} }, null, 2)); }}>{checkpoints.map((checkpoint) => <option key={checkpoint.id} value={checkpoint.id}>Step {checkpoint.sequence} · {new Date(checkpoint.created_at).toLocaleTimeString()} · {String(checkpoint.state.active_node_id ?? (Array.isArray(checkpoint.state.completed_nodes) ? checkpoint.state.completed_nodes[checkpoint.state.completed_nodes.length - 1] : undefined) ?? "snapshot")}</option>)}</select></label><label className="field"><span>Editable state variables · JSON</span><textarea rows={5} value={stateEdit} onChange={(event) => setStateEdit(event.target.value)} /></label><label className="field"><span>Prompt override (optional)</span><input value={replayPrompt} onChange={(event) => setReplayPrompt(event.target.value)} placeholder="Alternative instruction for the selected node" /></label><label className="field"><span>Model override (optional)</span><input value={replayModel} onChange={(event) => setReplayModel(event.target.value)} placeholder="provider/model" /></label><div className="approval-actions"><button className="button button-small" disabled={!checkpointId} onClick={() => void replayFromHere()}>Replay from here</button><button className="button button-small" disabled={!checkpointId} onClick={() => void forkComparison()}>Fork A/B comparison</button>{forkRuns && <button className="button button-small" onClick={() => void compareForks()}>Compare results</button>}</div>{forkStatus && <pre className="inline-message" role="status">{forkStatus}</pre>}</section><div className="trace-list">{events.length ? events.map((event) => <article className="trace-event" key={event.id}><span className={`trace-icon trace-icon--${event.type.toLowerCase().split("_")[0]}`}>{event.type === "FLOW_STATE_CHANGED" ? "↗" : event.type.includes("TERMINAL") ? "⌘" : event.type.includes("APPROVAL") ? "✓" : event.type.includes("CODE") ? "{ }" : "·"}</span><div className="trace-event__body"><div className="trace-event__meta"><strong>{eventTitle(event.type)}</strong><time>{new Date(event.occurred_at).toLocaleTimeString()}</time></div>{event.type === "SANDBOX_TERMINAL_OUTPUT" || event.type === "NEXUSGEN_CODE_GENERATED" ? <pre>{eventLabel(event)}</pre> : <p>{eventLabel(event)}</p>}</div></article>) : <div className="empty-state compact"><span className="empty-icon">◌</span><h3>Run events appear here</h3><p>Start a workflow to see active steps, team thoughts, code, and terminal output.</p></div>}</div></> : <div className="computer-view"><label className="field"><span>Sandbox computer ID</span><input value={sandboxId} onChange={(event) => setSandboxId(event.target.value)} placeholder="Computer UUID" /></label><div className="screen-frame">{frame ? <Image src={frame} alt="Live virtual computer desktop" width={1280} height={720} unoptimized style={{ width: "100%", height: "auto" }} /> : <div className="screen-placeholder"><span>▣</span><strong>Virtual desktop</strong><p>{screenStatus}</p></div>}</div><div className="screen-caption"><span className="live-indicator" /> {screenStatus}<span>·</span> Computer-scoped stream</div><div className="terminal-title"><span>⌘</span> LIVE TERMINAL OUTPUT</div><form className="terminal-command" onSubmit={(event) => void runTerminal(event)}><input aria-label="Terminal command" value={terminalCommand} onChange={(event) => setTerminalCommand(event.target.value)} placeholder="Computer UUID required · enter command" /><button className="button button-small" disabled={!sandboxId || !terminalCommand.trim()}>Run</button></form><pre className="terminal-view">{terminalOutput || events.filter((event) => event.type === "SANDBOX_TERMINAL_OUTPUT").map(eventLabel).join("\n") || "$ Waiting for sandbox output…"}</pre></div>}
    <div className="inspector-footnote">Events stream from this tenant’s private run channel.</div></aside>;
}
