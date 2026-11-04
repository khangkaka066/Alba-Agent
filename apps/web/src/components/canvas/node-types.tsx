"use client";

import { useState } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { apiRequest, readError } from "@/lib/api";
import { TIER_LABELS, groupAgentsByTier, hasTiers, parseJsonList, type TierEntry } from "@/lib/studio-spec.mjs";
import { DIFF_LABELS } from "@/lib/team-evolution.mjs";

export type CanvasKind = "start" | "crew" | "nexusgen" | "approval" | "router" | "rag";
export type NodeRunStatus = "IDLE" | "RUNNING" | "COMPLETED" | "WAITING_APPROVAL" | "ERROR";
export type ApprovalDecision = "allow_once" | "deny";

export type StudioNodeData = {
  label: string;
  description: string;
  config: Record<string, string>;
  active?: boolean;
  status?: NodeRunStatus;
  codePreview?: string;
  turn?: number;
  approvalId?: string;
  token?: string;
  diff?: "added" | "modified" | "removed";
  onApprovalResolved?: (approvalId: string) => void;
};

export type StudioNode = Node<StudioNodeData, CanvasKind>;

const nodeMeta: Record<CanvasKind, { label: string; tone: string }> = {
  start: { label: "Trigger", tone: "trigger" },
  crew: { label: "Agent team", tone: "crew" },
  nexusgen: { label: "Computer", tone: "sandbox" },
  approval: { label: "Approval", tone: "approval" },
  router: { label: "Router", tone: "router" },
  rag: { label: "Knowledge", tone: "knowledge" },
};

export function NodeIcon({ kind }: { kind: CanvasKind }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return <svg className="flow-node__icon" viewBox="0 0 24 24" aria-hidden="true" {...common}>
    {kind === "start" && <><path d="M5 18V6h14" /><path d="m13 6 6 6-6 6" /></>}
    {kind === "crew" && <><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0M16 6a3 3 0 0 1 0 5.8M17 14a4.5 4.5 0 0 1 3.5 4.4" /></>}
    {kind === "nexusgen" && <><path d="M8 4v5M16 4v5M8 15v5M16 15v5M4 8h5M15 8h5M4 16h5M15 16h5" /><path d="M9 9h6v6H9z" /></>}
    {kind === "approval" && <><path d="M12 3 20 6v5c0 5-3.4 8.2-8 10-4.6-1.8-8-5-8-10V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>}
    {kind === "router" && <><path d="M5 5v14M5 7h6a4 4 0 0 1 4 4v2a4 4 0 0 0 4 4h1M5 17h6a4 4 0 0 0 4-4V9a4 4 0 0 1 4-4h1" /></>}
    {kind === "rag" && <><path d="M5 4.5h12a2 2 0 0 1 2 2v13H7a2 2 0 0 1-2-2z" /><path d="M7 4.5v13a2 2 0 0 0 2 2M10 9h6M10 13h6" /></>}
  </svg>;
}

function statusLabel(status: NodeRunStatus): string {
  return { IDLE: "Idle", RUNNING: "Running", COMPLETED: "Completed", WAITING_APPROVAL: "Waiting approval", ERROR: "Error" }[status];
}

function parseList(value: string | undefined): unknown {
  try { return JSON.parse(value ?? "[]"); } catch { return []; }
}

function SpecialistRow({ agent }: { agent: TierEntry }) {
  return <li className="tier-agent">
    <strong>{agent.role}</strong>
    <small>{agent.model.split("/").at(-1)}</small>
    {agent.skills.length > 0 && <div className="tier-agent__row"><em>Skills</em>{agent.skills.map((skill) => <code key={skill}>{skill}</code>)}</div>}
    <div className="tier-agent__row"><em>Tools</em>{agent.tools.length ? agent.tools.map((tool) => <code key={tool}>{tool}</code>) : <span>none</span>}</div>
    {agent.paths.length > 0 && <div className="tier-agent__row"><em>Writes</em>{agent.paths.map((path) => <code key={path}>{path}</code>)}</div>}
  </li>;
}

function TierGroups({ config }: { config: Record<string, string> }) {
  const groups = groupAgentsByTier(parseList(config.agent_metadata), parseList(config.task_metadata));
  const contract = parseJsonList(config.expected_artifact_paths);
  const tiers = (["director", "lead", "specialist"] as const).filter((tier) => groups[tier].length > 0);
  return <div className="tier-groups">
    {tiers.map((tier) => <details key={tier} className={`tier-group tier-group--${tier} nodrag nowheel`} open={tier !== "specialist" && groups[tier].length <= 2}>
      <summary><span>{TIER_LABELS[tier]}{tier === "specialist" ? ` (${groups[tier].length})` : ""}</span><i aria-hidden="true">{groups[tier].length}</i></summary>
      <ul>{groups[tier].map((agent) => <SpecialistRow key={agent.id} agent={agent} />)}</ul>
    </details>)}
    {contract.length > 0 && <p className="tier-contract" title={contract.join("\n")}>Contract · {contract.length} {contract.length === 1 ? "file" : "files"}</p>}
  </div>;
}

function WorkflowNode({ data, selected, type }: NodeProps<StudioNode>) {
  const [decision, setDecision] = useState("");
  const [error, setError] = useState("");
  const kind = type as CanvasKind;
  const meta = nodeMeta[kind] ?? nodeMeta.crew;
  const status: NodeRunStatus = data.status ?? (data.active ? "RUNNING" : data.approvalId ? "WAITING_APPROVAL" : "IDLE");
  const classes = ["flow-node", `flow-node--${meta.tone}`, `flow-node--status-${status.toLowerCase()}`, selected ? "is-selected" : "", data.active ? "is-active" : "", data.diff ? `flow-node--diff-${data.diff}` : ""].filter(Boolean).join(" ");
  const config = data.config;
  const agentLines = (config.agents ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
  const agentRoles = agentLines.map((line) => line.split("|")[0]?.trim() || "Agent");
  const schemaNames = Array.from(new Set((config.task_metadata ?? "").match(/\"output_schema\"\s*:\s*\"([^\"]+)/g)?.map((value) => value.split("\"").at(-1) ?? "") ?? [])).filter(Boolean);
  const model = kind === "crew" ? config.model : kind === "nexusgen" ? config.coder_agent : "";
  const maxTurns = Math.max(1, Number(config.max_turns || 8));
  const approvalAction = async (next: ApprovalDecision) => {
    if (!data.approvalId || !data.token) return;
    setError(""); setDecision(next);
    try {
      await apiRequest(`/api/v1/approvals/${data.approvalId}/resolve`, data.token, { method: "POST", body: JSON.stringify({ decision: next }) });
      data.onApprovalResolved?.(data.approvalId);
    } catch (reason) { setError(readError(reason)); setDecision(""); }
  };

  return <article className={classes} aria-label={`${data.label}, ${statusLabel(status)}${data.diff ? `, ${DIFF_LABELS[data.diff]}` : ""}`}>
    {data.diff && <span className="flow-node__diff-badge">{DIFF_LABELS[data.diff]}</span>}
    {kind !== "start" && <Handle type="target" position={Position.Left} className="flow-handle" />}
    <header className="flow-node__header">
      <span className="flow-node__category"><NodeIcon kind={kind} /><span>{meta.label}</span></span>
      <span className={`node-status node-status--${status.toLowerCase()}`}><i />{statusLabel(status)}</span>
    </header>
    <div className="flow-node__title-row"><strong>{data.label}</strong>{model && <code className="model-pill">{model.split("/").at(-1)}</code>}</div>
    <p className="flow-node__description">{data.description}</p>

    {kind === "crew" && hasTiers(groupAgentsByTier(parseList(config.agent_metadata), [])) && <div className="flow-node__crew-body">
      <div className="agent-stack" aria-label={`${agentRoles.length} assigned agents`}><em>{agentRoles.length} agents</em><span className="node-tag node-tag--muted">{config.process === "hierarchical" ? "Hierarchical" : "Sequential"}</span></div>
      <TierGroups config={config} />
      <div className="flow-node__foot-row"><span>{config.join === "all" ? "Waits for all inputs" : "Starts on first input"}</span><code>{schemaNames[0] ?? "Structured output"}</code></div>
    </div>}
    {kind === "crew" && !hasTiers(groupAgentsByTier(parseList(config.agent_metadata), [])) && <div className="flow-node__crew-body">
      {agentRoles.length > 0 ? <div className="agent-stack" aria-label={`${agentRoles.length} assigned agents`}>{agentRoles.slice(0, 4).map((role, index) => <span key={`${role}-${index}`} title={role}>{role.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>)}{agentRoles.length > 4 && <small>+{agentRoles.length - 4}</small>}<em>{agentRoles.length} {agentRoles.length === 1 ? "agent" : "agents"}</em></div> : <div className="agent-stack agent-stack--empty"><span>+</span><em>Assign specialists in settings</em></div>}
      <div className="flow-node__tags">{agentRoles.slice(0, 3).map((role) => <span className="node-tag" key={role}>{role}</span>)}<span className="node-tag node-tag--muted">{config.process || "Sequential"}</span></div>
      <div className="flow-node__foot-row"><span>{config.tool_count ?? "0"} skills</span><code>{schemaNames[0] ?? config.output_schema ?? "Structured output"}</code></div>
    </div>}

    {kind === "nexusgen" && <div className="flow-node__sandbox-body"><div className="sandbox-line"><span className="node-tag node-tag--cyan">{(config.sandbox_provider || "docker").toUpperCase()}</span><span className="mono-note">{data.turn ? `Turn ${data.turn}/${maxTurns}` : `Up to ${maxTurns} turns`}</span></div>{parseJsonList(config.expected_artifact_paths).length > 0 && <p className="tier-contract" title={parseJsonList(config.expected_artifact_paths).join("\n")}>Contract · {parseJsonList(config.expected_artifact_paths).join(" · ")}</p>}<pre className="node-code-preview"><span>{status === "RUNNING" ? "Live task" : "main.py"}</span>{(data.codePreview || config.coder_instructions || "# Validate data, forecast revenue, and save charts").slice(0, 116)}</pre></div>}

    {kind === "approval" && <div className="flow-node__approval-body"><p>{config.boundary_rules?.split(/[\n,]/).filter(Boolean).slice(0, 2).join(" · ") || "Human review before continuing"}</p><div className="node-approval-actions"><button disabled={!data.approvalId || Boolean(decision)} onClick={() => void approvalAction("allow_once")}>{decision === "allow_once" ? "Approved" : "Approve"}</button><button disabled={!data.approvalId || Boolean(decision)} onClick={() => void approvalAction("deny")}>{decision === "deny" ? "Denied" : "Review"}</button></div>{error && <small className="node-error" role="alert">{error}</small>}</div>}

    {kind === "start" && <><div className="flow-upload-preview"><span aria-hidden="true">⇧</span><strong>CSV file upload</strong><small>Drop a file or add it as run input</small></div><div className="flow-node__foot-row"><span>{config.trigger_type || "manual"} trigger</span><code>Input schema</code></div></>}
    {kind === "router" && <div className="flow-node__foot-row"><span>{config.artifact_gate === "true" ? `Artifact gate · up to ${config.max_loop_iterations || 0} rework loops` : "Conditional branches"}</span><code>{(config.rules ?? "").split("\n").filter(Boolean).length || 1} routes</code></div>}
    {kind === "rag" && <div className="flow-node__foot-row"><span>{config.knowledge_base_ids ? "Workspace source attached" : "Attach a knowledge base"}</span><code>Top {config.top_k || "5"}</code></div>}
    <Handle type="source" position={Position.Right} className="flow-handle" />
  </article>;
}

export function StartTriggerNode(props: NodeProps<StudioNode>) { return <WorkflowNode {...props} />; }
export function CrewNode(props: NodeProps<StudioNode>) { return <WorkflowNode {...props} />; }
export function NexusGenSandboxNode(props: NodeProps<StudioNode>) { return <WorkflowNode {...props} />; }
export function ApprovalGateNode(props: NodeProps<StudioNode>) { return <WorkflowNode {...props} />; }
export function ConditionalRouterNode(props: NodeProps<StudioNode>) { return <WorkflowNode {...props} />; }
export function KnowledgeRAGNode(props: NodeProps<StudioNode>) { return <WorkflowNode {...props} />; }

export const nodeTypes = { start: StartTriggerNode, crew: CrewNode, nexusgen: NexusGenSandboxNode, approval: ApprovalGateNode, router: ConditionalRouterNode, rag: KnowledgeRAGNode };

export const kindMeta: Record<CanvasKind, { label: string; description: string }> = {
  start: { label: "Start trigger", description: "Start a workflow from an event" },
  crew: { label: "Crew team", description: "A team of specialists working together" },
  nexusgen: { label: "Computer task", description: "Code, verify, and run in a sandbox" },
  approval: { label: "Approval gate", description: "Pause for a human decision" },
  router: { label: "Conditional router", description: "Branch on workflow state" },
  rag: { label: "Knowledge search", description: "Retrieve tenant knowledge and tools" },
};

export const configFields: Record<CanvasKind, Array<{ key: string; label: string; placeholder: string; multiline?: boolean; choices?: string[] }>> = {
  start: [
    { key: "trigger_type", label: "Trigger type", placeholder: "Choose a trigger", choices: ["manual", "webhook", "schedule", "bot"] },
    { key: "input_schema", label: "Input JSON Schema", placeholder: "{ \"type\": \"object\", \"properties\": { \"question\": { \"type\": \"string\" } } }", multiline: true },
    { key: "schedule", label: "Schedule", placeholder: "0 9 * * 1-5" },
  ],
  crew: [
    { key: "consensus_enabled", label: "Adversarial consensus", placeholder: "true or false", choices: ["false", "true"] },
    { key: "consensus_models", label: "Independent models · one per line", placeholder: "openai/gpt-4.1-mini\nanthropic/claude-sonnet-4", multiline: true },
    { key: "arbiter_model", label: "Arbiter model", placeholder: "openai/gpt-4.1" },
    { key: "consensus_threshold", label: "Minimum confidence · 0–1", placeholder: "0.85" },
    { key: "agents", label: "Agents · role / goal / backstory", placeholder: "Researcher | Find reliable sources | Curious and precise", multiline: true },
    { key: "tasks", label: "Tasks", placeholder: "Research the request and prepare a concise answer", multiline: true },
    { key: "model", label: "LLM model", placeholder: "openai/gpt-4.1-mini" },
    { key: "output_schema", label: "Pydantic output schema name", placeholder: "NEXUSTaskOutput" },
  ],
  nexusgen: [
    { key: "consensus_enabled", label: "Adversarial consensus", placeholder: "true or false", choices: ["false", "true"] },
    { key: "consensus_models", label: "Independent models · one per line", placeholder: "openai/gpt-4.1-mini\nanthropic/claude-sonnet-4", multiline: true },
    { key: "arbiter_model", label: "Arbiter model", placeholder: "openai/gpt-4.1" },
    { key: "consensus_threshold", label: "Minimum confidence · 0–1", placeholder: "0.85" },
    { key: "coder_agent", label: "Coder model", placeholder: "openai/gpt-4.1-mini" },
    { key: "reviewer_agent", label: "Reviewer model", placeholder: "openai/gpt-4.1-mini" },
    { key: "coder_instructions", label: "Task", placeholder: "Analyze the dataset, forecast revenue, and save charts", multiline: true },
    { key: "reviewer_instructions", label: "Verification instructions", placeholder: "Inspect the implementation and verify the results", multiline: true },
    { key: "sandbox_provider", label: "Sandbox provider", placeholder: "Choose a provider", choices: ["docker", "e2b", "daytona"] },
    { key: "timeout_seconds", label: "Timeout · seconds", placeholder: "900" },
    { key: "max_turns", label: "Maximum turns", placeholder: "8" },
  ],
  approval: [
    { key: "boundary_rules", label: "Approval rules", placeholder: "external_email, destructive_command, high_spend", multiline: true },
    { key: "message", label: "Approval card message", placeholder: "Review this action before the workflow continues" },
  ],
  router: [
    { key: "field", label: "WorkflowState field", placeholder: "result.confidence" },
    { key: "operator", label: "Operator", placeholder: "equals, contains, greater_than" },
    { key: "rules", label: "Branch rules · one per line", placeholder: "result.approved == true → approved\nresult.score >= 0.8 → high_confidence", multiline: true },
  ],
  rag: [
    { key: "knowledge_base_ids", label: "Knowledge base IDs", placeholder: "One workspace knowledge-base UUID per line", multiline: true },
    { key: "mcp_servers", label: "Connected MCP servers", placeholder: "One approved server name per line", multiline: true },
    { key: "top_k", label: "Results to retrieve", placeholder: "5" },
  ],
};
