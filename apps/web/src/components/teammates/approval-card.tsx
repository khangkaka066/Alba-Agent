"use client";

import { useEffect, useRef, useState } from "react";
import { apiRequest, readError } from "@/lib/api";

export type PendingApproval = { approval_id: string; run_id?: string; node_id?: string; action?: string; rationale?: string; required_role?: string; routine_run_id?: string };

/** With `hotkeys`, the keys A (allow once), Y (always allow, routines only) and D (deny) answer this card while no text field has focus. */
export function ApprovalCard({ approval, token, onResolved, hotkeys = false }: { approval: PendingApproval; token: string; onResolved: (id: string) => void; hotkeys?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [healing, setHealing] = useState(false);
  const [original, setOriginal] = useState("");
  const [corrected, setCorrected] = useState("");
  const [feedback, setFeedback] = useState("");
  const decide = async (decision: "allow_once" | "always_allow_routine" | "deny") => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await apiRequest(`/api/v1/approvals/${approval.approval_id}/resolve`, token, { method: "POST", body: JSON.stringify({ decision, ...(healing && original && corrected && feedback ? { original_ai_output: original, human_corrected_output: corrected, feedback, agent_id: approval.node_id ? `${approval.node_id}_agent_1` : undefined } : {}) }) });
      onResolved(approval.approval_id);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  const latest = useRef<(decision: "allow_once" | "always_allow_routine" | "deny") => Promise<void>>(decide);
  latest.current = decide;
  useEffect(() => {
    if (!hotkeys) return;
    const press = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat) return;
      const target = event.target;
      if (target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return;
      const key = event.key.toLowerCase();
      const decision = key === "a" ? "allow_once" : key === "y" && approval.routine_run_id ? "always_allow_routine" : key === "d" ? "deny" : null;
      if (!decision) return;
      event.preventDefault();
      void latest.current(decision);
    };
    window.addEventListener("keydown", press);
    return () => window.removeEventListener("keydown", press);
  }, [hotkeys, approval.routine_run_id]);
  return <article className="approval-card"><div className="approval-card__top"><span className="approval-symbol">!</span><span className="pill pill-warning">Needs your review</span><span className="approval-card__id">{approval.node_id ?? "Workflow action"}</span></div><h3>{approval.action ?? "A workflow is waiting for approval"}</h3><p>{approval.rationale ?? "Review the requested boundary action before it continues."}</p><div className="approval-meta">Required role <strong>{approval.required_role ?? "builder"}</strong>{approval.run_id && <span>Run {approval.run_id.slice(0, 8)}</span>}</div><button className="button button-quiet" onClick={() => setHealing((value) => !value)}>{healing ? "Hide prompt correction" : "Suggest a prompt improvement"}</button>{healing && <div className="prompt-healing-fields"><label>Original agent output<textarea value={original} onChange={(event) => setOriginal(event.target.value)} rows={3} /></label><label>Your corrected output<textarea value={corrected} onChange={(event) => setCorrected(event.target.value)} rows={3} /></label><label>Why was it changed?<textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} rows={2} /></label><small>A reviewable prompt diff and quarantined learning capsule will be prepared with this decision.</small></div>}<div className="approval-actions"><button className="button button-primary" disabled={busy} onClick={() => void decide("allow_once")}>Allow once{hotkeys && <kbd className="approval-key">A</kbd>}</button>{approval.routine_run_id && <button className="button button-quiet" disabled={busy} onClick={() => void decide("always_allow_routine")}>Always allow{hotkeys && <kbd className="approval-key">Y</kbd>}</button>}<button className="button button-danger" disabled={busy} onClick={() => void decide("deny")}>Deny{hotkeys && <kbd className="approval-key">D</kbd>}</button></div>{error && <p className="inline-error">{error}</p>}</article>;
}
