"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest, readError } from "@/lib/api";

type Pair = {
  capsule_id: string;
  source_agent_id: string;
  target_agent_id: string;
  baseline: { applications: number; task_success_rate: number; retry_and_error_turns: number; human_approval_rejection_rate: number; average_tokens: number; average_latency_ms: number; tis_score: number } | null;
  treatment: { applications: number; task_success_rate: number; retry_and_error_turns: number; human_approval_rejection_rate: number; average_tokens: number; average_latency_ms: number; tis_score: number } | null;
};
type RadarData = { transfer_matrix: Pair[]; positive_transfer_pairs: number; negative_transfer_pairs: number; positive_transfer_rate: number; negative_transfer_rate: number; configured_policy_edges: number; auto_quarantined: Array<{ capsule_id: string; target_agent_id: string; tis_score: number; application_count: number; target_domain_tags: string[] }> };

export function LearningTransferRadar({ token }: { token: string }) {
  const [data, setData] = useState<RadarData | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const load = useCallback(() => { if (!token) return; void apiRequest<RadarData>("/api/v1/learning-transfer/telemetry", token).then((result) => { setData(result); setError(""); }).catch((reason: unknown) => setError(readError(reason))); }, [token]);
  useEffect(() => { load(); }, [load]);
  const restore = async (pair: Pair) => {
    try {
      await apiRequest(`/api/v1/learning-transfer/capsules/${pair.capsule_id}/targets/${encodeURIComponent(pair.target_agent_id)}/restore`, token, { method: "POST" });
      setMessage("Quarantine rolled back for this target pair."); load();
    } catch (reason) { setMessage(readError(reason)); }
  };
  return <section className="learning-radar">
    <div className="learning-radar__summary"><article className="panel-card"><span className="eyebrow">POSITIVE TRANSFER</span><strong>{data?.positive_transfer_pairs ?? "—"}</strong><small>{data ? `${(data.positive_transfer_rate * 100).toFixed(0)}% of measured capsule/target pairs` : "Capsule and target pairs with a positive impact score"}</small></article><article className="panel-card learning-radar__negative"><span className="eyebrow">AUTO QUARANTINED</span><strong>{data?.negative_transfer_pairs ?? "—"}</strong><small>{data ? `${(data.negative_transfer_rate * 100).toFixed(0)}% of measured pairs blocked after performance drops` : "Pairs blocked after measured negative transfer"}</small></article><article className="panel-card"><span className="eyebrow">LEARNING EDGES</span><strong>{data?.configured_policy_edges ?? "—"}</strong><small>Workspace propagation policies configured</small></article></div>
    <section className="panel-card learning-radar__table"><div className="section-heading"><div><span className="eyebrow">TRANSFER IMPACT MATRIX</span><h2>Source → target outcomes</h2></div><button className="button button-small" onClick={load}>Refresh</button></div>
      {error && <p className="inline-error">{error}</p>}{message && <p className="learning-radar__message" role="status">{message}</p>}
      {!data?.transfer_matrix.length ? <p className="muted-copy">No transfer observations have been recorded in this workspace yet.</p> : <div className="learning-radar__rows">{data.transfer_matrix.map((pair) => {
        const impact = pair.treatment?.tis_score ?? 0; const key = `${pair.capsule_id}:${pair.target_agent_id}`; const quarantined = data.auto_quarantined.some((item) => item.capsule_id === pair.capsule_id && item.target_agent_id === pair.target_agent_id);
        return <article className="learning-radar__row" key={key}><div className="learning-radar__pair"><span className={`transfer-dot ${quarantined ? "transfer-dot--negative" : impact > 0 ? "transfer-dot--positive" : ""}`} /><div><strong>{pair.source_agent_id} <span>→</span> {pair.target_agent_id}</strong><small>Capsule {pair.capsule_id.slice(0, 8)} · {quarantined ? "Quarantined" : impact > 0 ? "Positive" : "Collecting evidence"}</small></div></div><div className={`learning-radar__score ${quarantined ? "is-negative" : impact > 0 ? "is-positive" : ""}`}>{pair.treatment ? impact.toFixed(2) : "—"}<small>TIS</small></div><div className="learning-radar__actions"><button className="button button-small" onClick={() => setExpanded(expanded === key ? null : key)}>{expanded === key ? "Hide diff" : "Inspect diff"}</button>{quarantined && <button className="button button-small" onClick={() => void restore(pair)}>Restore with review</button>}</div>{expanded === key && <div className="learning-radar__diff"><div><b>Baseline without capsule</b><small>Success {((pair.baseline?.task_success_rate ?? 0) * 100).toFixed(0)}% · retries {(pair.baseline?.retry_and_error_turns ?? 0).toFixed(1)} · approval edits/denials {((pair.baseline?.human_approval_rejection_rate ?? 0) * 100).toFixed(0)}% · tokens {(pair.baseline?.average_tokens ?? 0).toFixed(0)} · latency {(pair.baseline?.average_latency_ms ?? 0).toFixed(0)} ms</small></div><div><b>Treatment with capsule</b><small>Success {((pair.treatment?.task_success_rate ?? 0) * 100).toFixed(0)}% · retries {(pair.treatment?.retry_and_error_turns ?? 0).toFixed(1)} · approval edits/denials {((pair.treatment?.human_approval_rejection_rate ?? 0) * 100).toFixed(0)}% · tokens {(pair.treatment?.average_tokens ?? 0).toFixed(0)} · latency {(pair.treatment?.average_latency_ms ?? 0).toFixed(0)} ms</small></div></div>}</article>;
      })}</div>}
    </section>
  </section>;
}
