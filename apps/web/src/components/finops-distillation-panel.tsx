"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest, readError } from "@/lib/api";

type Proposal = { id: string; workflow_id: string; agent_id: string; target_field: string; unified_diff: string; reviewer_comment: string; status: string };
type Recommendation = { id: string; agent_id: string; task_signature: string; candidate_model: string; metrics: Record<string, number>; few_shot_examples: Array<Record<string, unknown>>; status: string };

export function FinOpsDistillationPanel({ token }: { token: string }) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const [patches, candidates] = await Promise.all([
        apiRequest<Proposal[]>("/api/v1/self-healing/proposals", token),
        apiRequest<Recommendation[]>("/api/v1/analytics/distillation/recommendations", token),
      ]);
      setProposals(patches); setRecommendations(candidates);
    } catch (error) { setMessage(readError(error)); }
  }, [token]);
  useEffect(() => { void refresh(); }, [refresh]);
  const applyProposal = async (proposal: Proposal) => {
    try { const result = await apiRequest<{ version: number }>(`/api/v1/self-healing/proposals/${proposal.id}/apply`, token, { method: "POST" }); setMessage(`Prompt patch applied as workflow version ${result.version}.`); await refresh(); }
    catch (error) { setMessage(readError(error)); }
  };
  const applyRecommendation = async (row: Recommendation) => {
    try { await apiRequest(`/api/v1/analytics/distillation/recommendations/${row.id}/apply`, token, { method: "POST" }); setMessage(`Distilled model ${row.candidate_model} enabled.`); await refresh(); }
    catch (error) { setMessage(readError(error)); }
  };
  return <div className="distillation-panels"><section className="panel-card"><div className="section-heading"><div><span className="eyebrow">SELF-HEALING PROMPTS</span><h2>Review prompt improvements</h2></div><span className="pill">{proposals.length} pending</span></div>{proposals.length ? proposals.map((proposal) => <article className="distillation-card" key={proposal.id}><div><strong>{proposal.agent_id} · {proposal.target_field}</strong><p>{proposal.reviewer_comment}</p></div><details><summary>Inspect unified diff</summary><pre>{proposal.unified_diff}</pre></details><button className="button button-small button-primary" onClick={() => void applyProposal(proposal)}>Apply · create workflow version</button></article>) : <p className="muted-copy">Human corrections submitted on approval cards appear here as reviewable patches.</p>}</section><section className="panel-card"><div className="section-heading"><div><span className="eyebrow">AUTO-DISTILLATION</span><h2>Lower-cost model candidates</h2></div><span className="pill">{recommendations.length} recommendations</span></div>{recommendations.length ? recommendations.map((row) => <article className="distillation-card" key={row.id}><div><strong>{row.candidate_model}</strong><p>{row.agent_id} · {row.task_signature}</p></div><div className="distillation-metrics"><span>Parity {Number(row.metrics.semantic_similarity ?? 0).toFixed(2)}</span><span>Saving {Math.round(Number(row.metrics.cost_reduction ?? 0) * 100)}%</span><span>Speed {Number(row.metrics.latency_speedup ?? 0).toFixed(1)}×</span></div><details><summary>Few-shot examples ({row.few_shot_examples.length})</summary><pre>{JSON.stringify(row.few_shot_examples, null, 2)}</pre></details><button className="button button-small button-primary" disabled={row.status !== "recommended"} onClick={() => void applyRecommendation(row)}>{row.status === "recommended" ? "Switch model + few-shot" : row.status}</button></article>) : <p className="muted-copy">Candidates are surfaced after enough verified golden traces have been evaluated.</p>}</section>{message && <p className="inline-message" role="status">{message}</p>}</div>;
}
