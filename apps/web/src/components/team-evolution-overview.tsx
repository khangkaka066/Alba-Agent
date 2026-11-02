"use client";

import { useEffect, useState } from "react";
import { apiRequest, readError } from "@/lib/api";
import { POLICY_LABELS, trendGeometry } from "@/lib/team-evolution.mjs";

type LineageSummary = {
  lineage_id: string; name: string | null; lineage: string; active_workflow_id: string; auto_evolve_policy: string; pending_proposals: number;
  trend: Array<{ version: number; fitness: number }>;
  active: { version: number; fitness: number | null; artifact_completeness_rate: number | null; runs_observed: number } | null;
};

export function TeamEvolutionOverview({ token, onOpen }: { token: string; onOpen: (workflowId: string) => void }) {
  const [lineages, setLineages] = useState<LineageSummary[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!token) { setLineages([]); return; }
    let stopped = false;
    apiRequest<LineageSummary[]>("/api/v1/evolution/lineages", token).then((rows) => { if (!stopped) { setLineages(rows); setError(""); } }).catch((reason) => { if (!stopped) setError(readError(reason)); });
    return () => { stopped = true; };
  }, [token]);
  return <section className="panel-card team-evolution-overview" aria-label="Team evolution">
    <div className="section-heading"><div><span className="eyebrow">TEAM EVOLUTION</span><h2>How each team has changed</h2></div><span className="pill">{lineages.length} {lineages.length === 1 ? "team" : "teams"}</span></div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!lineages.length && !error && <p className="muted-copy">Evolve a workflow&apos;s team from the Studio and its generations, fitness trend and rollbacks will show here.</p>}
    {lineages.map((item) => {
      const { points, path } = trendGeometry(item.trend, 160, 44, 8);
      return <article className="distillation-card" key={item.lineage_id}>
        <div><strong>{item.name ?? "Workflow"}</strong><p>{item.lineage} · {POLICY_LABELS[item.auto_evolve_policy] ?? item.auto_evolve_policy}{item.pending_proposals ? ` · ${item.pending_proposals} proposal waiting` : ""}</p></div>
        <svg viewBox="0 0 160 44" width="160" height="44" role="img" aria-label="Fitness trend">{points.length > 1 && <path d={path} fill="none" stroke="#6366f1" strokeWidth="2" />}{points.map((point) => <circle key={point.version} cx={point.x} cy={point.y} r="3" fill="#6366f1" />)}</svg>
        <div className="distillation-metrics"><span>Active v{item.active?.version ?? "?"}</span><span>Fitness {item.active?.fitness != null ? `${Math.round(item.active.fitness * 100)}%` : "—"}</span><span>Artifacts {item.active?.artifact_completeness_rate != null ? `${Math.round(item.active.artifact_completeness_rate * 100)}%` : "—"}</span><span>{item.active?.runs_observed ?? 0} runs</span></div>
        <button className="button button-small button-primary" onClick={() => onOpen(item.active_workflow_id)}>Open in Studio</button>
      </article>;
    })}
  </section>;
}
