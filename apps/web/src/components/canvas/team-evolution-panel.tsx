"use client";

import { useEffect, useRef, useState } from "react";
import { apiRequest, readError, type JsonRecord } from "@/lib/api";
import { POLICY_LABELS, diffLines, fitnessDelta, trendGeometry, type TopologyDiff } from "@/lib/team-evolution.mjs";

export type Generation = {
  version: number; parent_version: number | null; workflow_id: string; status: "proposed" | "active" | "superseded" | "rolled_back" | "rejected";
  origin: string; is_active: boolean; evolution_rationale: string; mutation_ops_applied: Array<{ op: string; summary?: string }>;
  diagnoses: Array<{ kind: string; node_id: string; evidence: string[]; route_to: string }>; diff: TopologyDiff; decision_note: string | null;
  fitness: number | null; product_quality_score: number | null; artifact_completeness_rate: number | null; avg_human_rating: number | null;
  avg_cost_usd: number | null; avg_latency_seconds: number | null; runs_observed: number;
};
export type Lineage = {
  lineage_id: string; auto_evolve_policy: "SUGGEST_FIRST" | "FULLY_AUTONOMOUS"; active_workflow_id: string; active_version: number;
  generations: Generation[]; trend: Array<{ version: number; fitness: number }>; lineage: string;
};
type EvolveResult = { status: string; message?: string; generation?: Generation; diff_lines?: string[]; delegated?: unknown[]; lineage?: Lineage };

type Props = {
  token: string; workflowId: string; lineage: Lineage | null; evolveNonce: number;
  onChanged: (activeWorkflowId?: string) => void; onPreview: (generation: Generation) => void; onOpen: (workflowId: string) => void;
  onMessage: (message: string) => void; onClose: () => void;
};

const STATUS_LABEL: Record<Generation["status"], string> = { proposed: "Proposal", active: "Active", superseded: "Superseded", rolled_back: "Rolled back", rejected: "Rejected" };
const pct = (value: number | null) => value === null ? "—" : `${Math.round(value * 100)}%`;

function Trend({ lineage }: { lineage: Lineage }) {
  const { points, path } = trendGeometry(lineage.trend, 280, 84);
  if (!points.length) return <p className="muted-copy">Fitness appears after the first finished run of each generation.</p>;
  return <svg className="evolution-trend" viewBox="0 0 280 84" role="img" aria-label={`Product fitness by generation: ${points.map((point) => `v${point.version} ${pct(point.fitness)}`).join(", ")}`}>
    <line x1="12" x2="268" y1="12" y2="12" /><line x1="12" x2="268" y1="72" y2="72" />
    {points.length > 1 && <path d={path} />}
    {points.map((point) => <g key={point.version}><circle cx={point.x} cy={point.y} r="4" /><text x={point.x} y={Math.min(80, point.y + 14)} textAnchor="middle">v{point.version}</text></g>)}
  </svg>;
}

export function TeamEvolutionPanel({ token, workflowId, lineage, evolveNonce, onChanged, onPreview, onOpen, onMessage, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EvolveResult | null>(null);
  const handled = useRef(0);
  const proposal = lineage?.generations.find((item) => item.status === "proposed");

  const run = async (action: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    try { await action(); if (success) onMessage(success); }
    catch (error) { onMessage(readError(error)); }
    finally { setBusy(false); }
  };
  const evolve = () => run(async () => {
    const response = await apiRequest<EvolveResult>(`/api/v1/workflows/${workflowId}/evolve`, token, { method: "POST", body: JSON.stringify({}) });
    setResult(response);
    onMessage(response.status === "promoted" ? "A new team generation was promoted." : response.status === "proposed" ? "A team evolution proposal is ready for review." : response.message ?? "No structural change is justified yet.");
    onChanged(response.status === "promoted" ? response.generation?.workflow_id : undefined);
  });
  useEffect(() => { if (evolveNonce > handled.current) { handled.current = evolveNonce; void evolve(); } }, [evolveNonce]); // eslint-disable-line react-hooks/exhaustive-deps

  const decide = (generation: Generation, action: "promote" | "reject" | "rollback", success: string) => run(async () => {
    await apiRequest(`/api/v1/workflows/${workflowId}/generations/${generation.version}/${action}`, token, { method: "POST", body: JSON.stringify({}) });
    setResult(null);
    onChanged(action === "reject" ? undefined : generation.workflow_id);
  }, success);
  const setPolicy = (value: string) => run(async () => {
    await apiRequest(`/api/v1/workflows/${workflowId}/evolution-policy`, token, { method: "PUT", body: JSON.stringify({ auto_evolve_policy: value }) });
    onChanged();
  }, value === "FULLY_AUTONOMOUS" ? "Autonomous mode on: new generations are promoted and regressions roll back automatically." : "Suggest-first mode: every change waits for your approval.");

  return <aside className="evolution-panel" aria-label="Team generations">
    <header><div><span className="eyebrow">TEAM EVOLUTION</span><h2>{lineage?.lineage || "v1"}</h2></div><button className="button button-small" onClick={onClose} aria-label="Close team generations">×</button></header>
    <div className="evolution-actions">
      <button className="button button-primary button-small" disabled={busy} onClick={() => void evolve()}>{busy ? "Analysing…" : "Evolve Team Topology"}</button>
      <label>Governance<select aria-label="Evolution governance" value={lineage?.auto_evolve_policy ?? "SUGGEST_FIRST"} disabled={busy} onChange={(event) => void setPolicy(event.target.value)}>
        {Object.entries(POLICY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
    </div>
    {lineage && <Trend lineage={lineage} />}
    {proposal && <section className="evolution-proposal" aria-label="Team evolution proposal">
      <strong>Team Evolution Proposal · v{proposal.version}</strong>
      <p>{proposal.evolution_rationale}</p>
      <ul>{diffLines(proposal.diff).map((line) => <li key={line.text} className={`diff-line diff-line--${line.tone}`}>{line.text}</li>)}</ul>
      {proposal.diagnoses.length > 0 && <details><summary>Why · {proposal.diagnoses.length} finding{proposal.diagnoses.length === 1 ? "" : "s"}</summary><ul>{proposal.diagnoses.slice(0, 6).map((item) => <li key={`${item.kind}-${item.node_id}`}><b>{item.kind.replace(/_/g, " ").toLowerCase()}</b> · {item.node_id}<br /><small>{item.evidence[0]}</small></li>)}</ul></details>}
      <div className="evolution-actions"><button className="button button-small" onClick={() => onPreview(proposal)}>Preview graph diff</button><button className="button button-primary button-small" disabled={busy} onClick={() => void decide(proposal, "promote", `v${proposal.version} is now the active team.`)}>Approve</button><button className="button button-small" disabled={busy} onClick={() => void decide(proposal, "reject", `v${proposal.version} was rejected.`)}>Reject</button></div>
    </section>}
    {result?.status === "no_change" && <p className="inline-message">{result.message}</p>}
    {result && result.delegated && result.delegated.length > 0 && <p className="inline-message">{result.delegated.length} finding(s) are prompt or skill problems; they were sent to Self-Healing instead of changing the team.</p>}
    <ol className="evolution-list">
      {[...(lineage?.generations ?? [])].reverse().map((generation) => {
        const parent = lineage?.generations.find((item) => item.version === generation.parent_version);
        const delta = fitnessDelta(generation, parent);
        return <li key={generation.version} className={`evolution-gen evolution-gen--${generation.status}`}>
          <div className="evolution-gen__head"><strong>v{generation.version}</strong><span className={`pill pill-${generation.status}`}>{STATUS_LABEL[generation.status]}</span>{generation.origin !== "baseline" && <small>{generation.origin.replace("_", "-")}</small>}</div>
          <p>{generation.evolution_rationale}</p>
          <div className="evolution-metrics">
            <span title="Product fitness">Fitness <b>{pct(generation.fitness)}</b>{delta !== null && <i className={delta >= 0 ? "up" : "down"}>{delta >= 0 ? "▲" : "▼"} {Math.abs(Math.round(delta * 100))}</i>}</span>
            <span>Artifacts <b>{pct(generation.artifact_completeness_rate)}</b></span>
            <span>Quality <b>{pct(generation.product_quality_score)}</b></span>
            <span>Runs <b>{generation.runs_observed}</b></span>
            {generation.avg_cost_usd !== null && <span>Cost <b>${generation.avg_cost_usd.toFixed(3)}</b></span>}
          </div>
          {generation.mutation_ops_applied.length > 0 && <div className="evolution-ops">{generation.mutation_ops_applied.map((op, index) => <code key={index} title={op.summary}>{op.op.replace(/_/g, " ").toLowerCase()}</code>)}</div>}
          <div className="evolution-actions">
            {generation.status !== "proposed" && !generation.is_active && <button className="button button-small" onClick={() => onOpen(generation.workflow_id)}>Open</button>}
            {generation.parent_version !== null && <button className="button button-small" onClick={() => onPreview(generation)}>Diff</button>}
            {!generation.is_active && generation.status !== "proposed" && generation.status !== "rejected" && <button className="button button-small" disabled={busy} onClick={() => void decide(generation, "rollback", `Restored v${generation.version}.`)}>Roll back to v{generation.version}</button>}
          </div>
          {generation.decision_note && <small className="muted-copy">{generation.decision_note}</small>}
        </li>;
      })}
    </ol>
  </aside>;
}

export type EvolutionJson = JsonRecord;
