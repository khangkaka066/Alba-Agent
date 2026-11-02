"use client";

import { useState } from "react";
import { apiRequest, readError } from "@/lib/api";

export type PendingApproval = { approval_id: string; run_id?: string; node_id?: string; action?: string; rationale?: string; required_role?: string; routine_run_id?: string };

export function ApprovalCard({ approval, token, onResolved }: { approval: PendingApproval; token: string; onResolved: (id: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [healing, setHealing] = useState(false);
  const [original, setOriginal] = useState("");
  const [corrected, setCorrected] = useState("");
  const [feedback, setFeedback] = useState("");
  const decide = async (decision: "allow_once" | "always_allow_routine" | "deny") => {
    setBusy(true); setError("");
    try {
      await apiRequest(`/api/v1/approvals/${approval.approval_id}/resolve`, token, { method: "POST", body: JSON.stringify({ decision, ...(healing && original && corrected && feedback ? { original_ai_output: original, human_corrected_output: corrected, feedback, agent_id: approval.node_id ? `${approval.node_id}_agent_1` : undefined } : {}) }) });
      onResolved(approval.approval_id);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  return <article className="approval-card"><div className="approval-card__top"><span className="approval-symbol">!</span><span className="pill pill-warning">Needs your review</span><span className="approval-card__id">{approval.node_id ?? "Workflow action"}</span></div><h3>{approval.action ?? "A workflow is waiting for approval"}</h3><p>{approval.rationale ?? "Review the requested boundary action before it continues."}</p><div className="approval-meta">Required role <strong>{approval.required_role ?? "builder"}</strong>{approval.run_id && <span>Run {approval.run_id.slice(0, 8)}</span>}</div><button className="button button-quiet" onClick={() => setHealing((value) => !value)}>{healing ? "Hide prompt correction" : "Suggest a prompt improvement"}</button>{healing && <div className="prompt-healing-fields"><label>Original agent output<textarea value={original} onChange={(event) => setOriginal(event.target.value)} rows={3} /></label><label>Your corrected output<textarea value={corrected} onChange={(event) => setCorrected(event.target.value)} rows={3} /></label><label>Why was it changed?<textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} rows={2} /></label><small>A reviewable prompt diff and quarantined learning capsule will be prepared with this decision.</small></div>}<div className="approval-actions"><button className="button button-primary" disabled={busy} onClick={() => void decide("allow_once")}>Allow once</button>{approval.routine_run_id && <button className="button button-quiet" disabled={busy} onClick={() => void decide("always_allow_routine")}>Always allow</button>}<button className="button button-danger" disabled={busy} onClick={() => void decide("deny")}>Deny</button></div>{error && <p className="inline-error">{error}</p>}</article>;
}
