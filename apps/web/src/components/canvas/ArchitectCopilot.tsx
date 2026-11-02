"use client";

import { useLocale } from "@/components/locale-provider";
import { useEffect, useState } from "react";
import { apiRequest, readError, type JsonRecord } from "@/lib/api";
import { RIGOR_OPTIONS } from "@/lib/studio-spec.mjs";

type Rigor = (typeof RIGOR_OPTIONS)[number]["value"];

type ArchitectResult = {
  workflow_spec: JsonRecord;
  summary: string;
  design_reasoning: string[];
  agents: Array<{ id: string; role: string; model: string; tier?: string; tools: string[]; knowledge_capsules: string[] }>;
  rigor?: string;
  agent_count?: number;
  departments?: Array<{ id: string; label: string; agents: number }>;
  tools: string[];
  knowledge_capsules: string[];
  structural_diff?: { added_nodes: string[]; modified_nodes: string[]; removed_nodes: string[] };
};

type Props = {
  token: string;
  currentWorkflow?: JsonRecord;
  empty: boolean;
  onApply: (spec: JsonRecord) => void;
  onRunGenerated: (spec: JsonRecord, runId: string) => void;
  onUndo: (spec?: JsonRecord) => void;
};

export function ArchitectCopilot({ token, currentWorkflow, empty, onApply, onRunGenerated, onUndo }: Props) {
  const { t } = useLocale();
  const [open, setOpen] = useState(empty);
  const [prompt, setPrompt] = useState("");
  const [rigor, setRigor] = useState<Rigor>("auto");
  const [result, setResult] = useState<ArchitectResult | null>(null);
  const [previous, setPrevious] = useState<JsonRecord | null>(null);
  const [applied, setApplied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { if (empty) setOpen(true); }, [empty]);

  const generate = async (autoRun: boolean) => {
    if (!token || !prompt.trim()) return;
    setBusy(true); setError(""); setResult(null); setApplied(false);
    setPhase("Breaking the requirement into stages…");
    const timer = window.setTimeout(() => setPhase("Binding workspace tools, knowledge, and verified learning…"), 800);
    try {
      const response = currentWorkflow
        ? await apiRequest<ArchitectResult & { run_id?: string }>("/api/v1/architect/refine-workflow", token, {
            method: "POST", body: JSON.stringify({ current_workflow_spec: currentWorkflow, edit_instruction: prompt }),
          })
        : await apiRequest<ArchitectResult & { run_id?: string }>("/api/v1/architect/generate-workflow", token, {
            method: "POST", body: JSON.stringify({ user_requirement_prompt: prompt, auto_run: autoRun, ...(rigor === "auto" ? {} : { rigor }) }),
          });
      window.clearTimeout(timer);
      setPhase("Validating the graph and arranging the canvas…");
      setResult(response);
      setPrevious(currentWorkflow ?? null);
      if (response.run_id) { onRunGenerated(response.workflow_spec, response.run_id); setApplied(true); setPhase("Team is running. Live execution is open."); }
      else setPhase("Design is ready to review.");
    } catch (reason) {
      window.clearTimeout(timer); setPhase(""); setError(readError(reason));
    } finally { setBusy(false); }
  };

  const apply = () => {
    if (!result) return;
    onApply(result.workflow_spec); setApplied(true);
  };
  const undo = () => {
    onUndo(previous ?? undefined); setApplied(false); setResult(null); setPhase("Previous canvas restored.");
  };

  return <section className={`architect-copilot ${empty ? "architect-copilot--hero" : ""}`}>
    <header className="architect-copilot__head">
      <div><span className="eyebrow">CANVAS COPILOT</span><strong>{empty ? "Build a team with AI" : "AI Architect Copilot"}</strong></div>
      {!empty && <button className="button button-small" onClick={() => setOpen((value) => !value)}>{open ? "Collapse" : "Open copilot"}</button>}
    </header>
    {open && <>
      <label className="field"><span>{currentWorkflow ? "Describe a canvas edit" : "What should this team do?"}</span>
        <textarea rows={empty ? 3 : 2} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={t("architect.placeholder")} />
      </label>
      {!currentWorkflow && <label className="field architect-rigor"><span>Studio scale</span>
        <select aria-label="Studio scale" value={rigor} onChange={(event) => setRigor(event.target.value as Rigor)} disabled={busy}>
          {RIGOR_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>}
      <div className="architect-copilot__actions"><button className="button button-primary" disabled={!token || !prompt.trim() || busy} onClick={() => void generate(!currentWorkflow)}>{busy ? "Preparing…" : currentWorkflow ? "Refine workflow" : "Generate & Run Now"}</button>{!currentWorkflow && <button className="button button-small" disabled={!token || !prompt.trim() || busy} onClick={() => void generate(false)}>Generate Blueprint Only</button>}{phase && <span role="status">{phase}</span>}</div>
      {error && <p className="inline-error">{error}</p>}
      {result && <div className="architect-result">
        <strong>{result.summary}</strong>
        {result.design_reasoning.length > 0 && <ol>{result.design_reasoning.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ol>}
        <div className="architect-result__meta"><span>{result.agent_count ?? result.agents.length} agents</span>{result.rigor && <span>{result.rigor.replace("_", " ")}</span>}{result.departments && <span>{result.departments.length} departments</span>}<span>{result.tools.length} tools</span><span>{result.knowledge_capsules.length} verified capsules</span></div>
        {result.structural_diff && <p>Graph diff · +{result.structural_diff.added_nodes.length} nodes · ~{result.structural_diff.modified_nodes.length} changed · −{result.structural_diff.removed_nodes.length} removed</p>}
        <div className="architect-copilot__actions"><button className="button button-primary" disabled={applied} onClick={apply}>{applied ? "Applied to canvas" : "Apply to canvas"}</button>{(previous || applied) && <button className="button button-quiet" onClick={undo}>Undo</button>}</div>
      </div>}
    </>}
  </section>;
}
