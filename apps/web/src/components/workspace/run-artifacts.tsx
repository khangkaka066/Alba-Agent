"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { useShell } from "@/components/shell/shell-context";
import type { JsonRecord } from "@/lib/api";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { checkpointForStep } from "@/lib/artifact-review.mjs";
import { MediaView } from "./media-view";
import { isHtmlArtifact } from "./html-artifact-preview";
import { ImplementationPlanArtifact } from "./plan-proposal";
import { useWorkspace } from "./workspace-context";

export function specNodes(spec: JsonRecord | null): JsonRecord[] {
  return Array.isArray(spec?.nodes) ? spec.nodes.filter((node): node is JsonRecord => node !== null && typeof node === "object") : [];
}

export function CheckpointActions({ text, checkpoint, runId }: { text: string; checkpoint?: string; runId?: string }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [copied, setCopied] = useState(false);
  useEffect(() => { if (!copied) return; const timer = window.setTimeout(() => setCopied(false), 1500); return () => window.clearTimeout(timer); }, [copied]);
  return <div className="ag-checkpoint-actions" role="group" aria-label={t("studio.checkpointActions")}>
    {checkpoint && runId && <><button type="button" disabled={workspace.busy} title={t("studio.restoreHint")} onClick={() => void workspace.replay(runId, checkpoint, false)}><Icon name="refresh" size={13} />{t("studio.restore")}</button>
    <button type="button" disabled={workspace.busy} title={t("studio.forkHint")} onClick={() => void workspace.replay(runId, checkpoint, true)}><Icon name="canvas" size={13} />{t("studio.fork")}</button></>}
    <button type="button" aria-label={t("common.copy")} onClick={() => void navigator.clipboard.writeText(text).then(() => setCopied(true)).catch(() => setCopied(false))}><Icon name={copied ? "check" : "copy"} size={13} /></button>
  </div>;
}

export function TaskListArtifact() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const nodes = specNodes(workspace.spec).filter((node) => node.kind !== "start");
  const done = nodes.filter((node) => workspace.run.completed.includes(String(node.id))).length;
  return <section className="ag-artifact-card" aria-label={t("studio.taskList")}>
    <header><Icon name="check" /><h3>{t("studio.taskList")}</h3><span>{done} / {nodes.length}</span></header>
    <progress max={nodes.length || 1} value={done} aria-label={t("studio.taskProgress")} />
    <ol className="ag-task-list">{nodes.map((node) => {
      const id = String(node.id), complete = workspace.run.completed.includes(id), active = workspace.run.active.includes(id);
      const checkpoint = checkpointForStep(workspace.checkpoints, id);
      const agent = Array.isArray(node.agents) ? node.agents[0] as JsonRecord | undefined : undefined;
      return <li key={id} className={active ? "is-running" : complete ? "is-complete" : ""}>
        <span className="ag-step-check" aria-label={t(complete ? "studio.done" : active ? "studio.inProgress" : "studio.pending")}>{complete ? <Icon name="check" size={13} /> : active ? "/" : ""}</span>
        <div><strong>{String(node.label ?? node.kind)}</strong><small>{agent ? String(agent.role ?? "") : String(node.kind)}{checkpoint ? ` · ${new Date(checkpoint.created_at).toLocaleTimeString()}` : ""}</small>
          {complete && <CheckpointActions text={String(node.label ?? id)} runId={workspace.runId ?? undefined} checkpoint={checkpoint?.id} />}</div>
        <StepElapsed start={workspace.nodeTimes[id]?.start} end={workspace.nodeTimes[id]?.end} />
        {agent && <span className="ag-agent-avatar" title={String(agent.role ?? "")}>{String(agent.role ?? "A").slice(0, 1)}</span>}
      </li>;
    })}</ol>
    {!nodes.length && <p className="ag-empty">{t("studio.noPlan")}</p>}
  </section>;
}

/** Runtime reports node-level tool calls; missing per-agent counters stay explicitly unmeasured. */
export function LiveAgentTree() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const nodes = specNodes(workspace.spec);
  const jump = workspace.focusNode;
  return <div className="ag-agent-tree" aria-label={t("studio.liveTree")}>
    {(["director", "lead", "specialist"] as const).map((tier, index) => {
      const entries = nodes.flatMap((node) => {
        const agents = Array.isArray(node.agents) ? node.agents as JsonRecord[] : node.kind === "sandbox" ? [{ id: `${node.id}-coder`, role: t("studio.coder"), tier: "specialist" }, { id: `${node.id}-reviewer`, role: t("studio.reviewer"), tier: "specialist" }] : [];
        return agents.filter((agent) => (agent.tier ?? "specialist") === tier).map((agent) => ({ node, agent }));
      });
      if (!entries.length) return null;
      return <details key={tier} open className={`ag-agent-tier ag-agent-tier--${index + 1}`}><summary>{t(`studio.tier.${tier}`)} <span>{entries.length}</span></summary>
        <ul>{entries.map(({ node, agent }) => {
          const id = String(node.id), active = workspace.run.active.includes(id), complete = workspace.run.completed.includes(id);
          const tool = active ? workspace.run.tools.filter((item) => item.node === id).at(-1) : null;
          return <li key={`${id}-${agent.id}`}><button type="button" title={t("studio.jumpCanvas")} onClick={() => jump(id)}><span className={`run-dot run-dot--${complete ? "completed" : active ? "running" : "idle"}`} /><span><strong>{String(agent.role ?? agent.name ?? agent.id)}</strong><small>{String(node.label ?? node.kind)} · {tool?.name ?? t(complete ? "studio.done" : active ? "studio.inProgress" : "studio.pending")}</small></span><StepElapsed start={workspace.nodeTimes[id]?.start} end={workspace.nodeTimes[id]?.end} /><Icon name="canvas" size={13} /></button>
            {active && <button type="button" className="ag-iconbtn" aria-label={t("dock.terminal")} onClick={() => { workspace.setMode("editor"); shell.showDock("terminal"); }}><Icon name="terminal" size={13} /></button>}</li>;
        })}</ul>
      </details>;
    })}
  </div>;
}

export function WalkthroughAndProofArtifact() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const proofs = workspace.artifacts.filter((file) => /(^|\/)qa\/evidence\//i.test(file.filename));
  const media = workspace.artifacts.filter((file) => ["video", "image", "audio"].includes(classifyArtifact(file.filename, file.mime_type).kind));
  const expected = [...new Set(specNodes(workspace.spec).flatMap((node) => Array.isArray(node.expected_artifact_paths) ? node.expected_artifact_paths.map(String) : []))];
  return <section className="ag-artifact-card ag-walkthrough" aria-label={t("studio.walkthrough")}>
    <header><Icon name="shield" /><h3>{t("studio.walkthrough")}</h3><span>{specNodes(workspace.spec).filter((node) => node.kind !== "start" && workspace.run.completed.includes(String(node.id))).length} {t("studio.stepsComplete")}</span></header>
    <p>{String(workspace.spec?.name ?? t("studio.deliverables"))}</p>
    {expected.length > 0 && <ul className="ag-proof-contracts">{expected.map((path) => <li key={path}><Icon name={workspace.artifacts.some((file) => file.filename === path) ? "check" : "file"} size={14} /><span>{path}</span><small>{t(workspace.artifacts.some((file) => file.filename === path) ? "studio.produced" : "studio.missing")}</small></li>)}</ul>}
    <div className="ag-proof-badges">{proofs.length ? proofs.map((file) => <button type="button" className="ag-chip" key={file.filename} onClick={() => workspace.select(file.filename)}><Icon name="file" size={13} />{file.filename}</button>) : null}</div>
    <div className="ag-proof-gallery">{media.map((file) => <figure key={file.filename}><MediaView artifact={file} kind={classifyArtifact(file.filename, file.mime_type).kind} /><figcaption>{file.filename}</figcaption></figure>)}</div>

  </section>;
}

export function RunArtifacts() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const shell = useShell();
  const open = (file: typeof workspace.artifacts[number]) => { workspace.select(file.filename); workspace.setArtifactView("preview"); shell.showDock(isHtmlArtifact(file) ? "browser" : "files"); };
  if (workspace.artifacts.length === 0 && !workspace.plan) return <div className="nx-pane-empty"><Icon name="file" size={26} /><h3>{t("interface.noArtifacts")}</h3><p>{t("interface.noArtifactsBody")}</p></div>;
  return <div className="ag-artifact-gallery">
    {workspace.artifacts.map((file) => <div key={file.filename}><button type="button" onClick={() => open(file)}><Icon name="file" size={15} /><span>{file.filename}</span><small>{(file.size_bytes / 1024).toFixed(1)} KB</small></button><button type="button" className="ag-chip" onClick={() => open(file)}>{t(isHtmlArtifact(file) ? "result.previewLive" : "result.preview")}</button></div>)}
  </div>;
}

export function ArtifactDock() {
  const workspace = useWorkspace();
  return <div className="ag-artifact-dock">{workspace.plan && <ImplementationPlanArtifact spec={workspace.plan.spec} pending />}<RunArtifacts /></div>;
}


function StepElapsed({ start, end }: { start?: number; end?: number }) {
  const { t } = useLocale();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!start || end) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [start, end]);
  return <span className="ag-step-elapsed" title={`${t("studio.elapsed")} · ${t("studio.tokens")}: ${t("studio.unmeasured")}`}>{start ? `${Math.max(0, Math.floor(((end ?? now) - start) / 1000))}s` : "—"}</span>;
}
