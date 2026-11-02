"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { addEdge, Background, BackgroundVariant, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState, type Connection, type Edge, type ReactFlowInstance } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ApiError, apiRequest, downloadFile, readError, type JsonRecord } from "@/lib/api";
import { toYaml } from "@/lib/workflow-format.mjs";
import { OPERATOR_CODES, parseJsonList, routesToText } from "@/lib/studio-spec.mjs";
import { diffStatuses, type DiffStatus } from "@/lib/team-evolution.mjs";
import { TeamEvolutionPanel, type Generation, type Lineage } from "./team-evolution-panel";
import { ConfigDrawer } from "./config-drawer";
import { ArchitectCopilot } from "./ArchitectCopilot";
import { kindMeta, nodeTypes, NodeIcon, type CanvasKind, type StudioNode, type StudioNodeData } from "./node-types";
import type { PendingApproval } from "@/components/teammates/approval-card";
import { RunArtifactGallery } from "@/components/inspector/run-artifact-gallery";

type WorkflowEnvelope = { id: string; run_id: string; workflow_id?: string; status?: string };
type RunSelection = { workflowId: string; runId: string };
type SavedWorkflow = { id: string; name: string; version: number };
type RunHistory = { id: string; workflow_id: string; status: string; created_at: string; artifacts: Array<{ filename: string }> };
type Props = { embedded?: boolean; token: string; scope: { tenant_id: string; workspace_id: string }; activeNodeId?: string; openWorkflowId?: string | null; approvals?: PendingApproval[]; onApprovalResolved?: (id: string) => void; onRun: (run: RunSelection) => void; onModal: (modal: "api-key" | "widget") => void };

// The canvas always shows the active run's generated WorkflowSpec; there is no built-in demo graph.
const initialNodes: StudioNode[] = [];
const initialEdges: Edge[] = [];

function textValue(value: unknown, fallback: string): string { return typeof value === "string" && value.length > 0 ? value : fallback; }
function configList(value: string | undefined): string[] { return (value ?? "").split(/[\n,]/).map((part) => part.trim()).filter(Boolean); }
function identifier(): string { return crypto.randomUUID(); }
function consensusConfig(config: Record<string, string>) { return { enabled: config.consensus_enabled === "true", models: (config.consensus_models ?? "").split("\n").map((model) => model.trim()).filter(Boolean), arbiter_model: config.arbiter_model ?? "", min_agreement_threshold: Number(config.consensus_threshold || 0.85) }; }

function contractFields(c: Record<string, string>) {
  return { join: c.join === "all" ? "all" : "any", expected_artifact_paths: parseJsonList(c.expected_artifact_paths), requires_visual_evidence: c.requires_visual_evidence === "true" };
}

function makeSpec(nodes: StudioNode[], edges: Edge[], scope: { tenant_id: string; workspace_id: string }, workflowId = identifier(), name = "Untitled workflow", learning = { scope: "CREW_LOCAL", allowHeuristics: true, allowCodePatterns: false, requireApproval: false }, modes?: JsonRecord): JsonRecord {
  const mapped = nodes.map((node) => {
    const c = node.data.config;
    if (node.type === "start") {
      let inputSchema: Record<string, unknown> = {};
      try { const parsed = JSON.parse(c.input_schema ?? "{}"); if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) inputSchema = parsed as Record<string, unknown>; }
      catch { inputSchema = {}; }
      return { id: node.id, kind: "start", label: node.data.label, trigger_type: c.trigger_type || "manual", input_schema: inputSchema, schedule: c.schedule || null };
    }
    if (node.type === "crew") {
      const agentLines = (c.agents ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
      let agentMetadata: JsonRecord[] = [];
      let taskMetadata: JsonRecord[] = [];
      try { agentMetadata = JSON.parse(c.agent_metadata ?? "[]") as JsonRecord[]; } catch { agentMetadata = []; }
      try { taskMetadata = JSON.parse(c.task_metadata ?? "[]") as JsonRecord[]; } catch { taskMetadata = []; }
      const agentsUnchanged = agentMetadata.length > 0 && c.agents === c.agents_source;
      const agents = agentLines.length ? agentLines.map((line, index) => {
        const [role, goal, backstory] = line.split("|").map((part) => part.trim());
        const metadata = agentMetadata[index] ?? {};
        const preservedId = agentsUnchanged && typeof metadata.id === "string" ? metadata.id : `${node.id}_agent_${index + 1}`;
        const skillsEdited = index === 0 && c.skill_ids !== c.skill_ids_source;
        const toolsEdited = index === 0 && c.tool_ids !== c.tool_ids_source;
        return { ...metadata, id: preservedId, role: role || `Specialist ${index + 1}`, goal: goal || "Complete the assigned workflow task", backstory: backstory || "", model: textValue(String(metadata.model ?? c.model ?? ""), "openai/gpt-4.1-mini"), skill_ids: index === 0 && (skillsEdited || !agentsUnchanged) ? configList(c.skill_ids) : Array.isArray(metadata.skill_ids) ? metadata.skill_ids : [], tool_ids: index === 0 && (toolsEdited || !agentsUnchanged) ? configList(c.tool_ids) : Array.isArray(metadata.tool_ids) ? metadata.tool_ids : [] };
      }) : [{ id: `${node.id}_agent_1`, role: "Research specialist", goal: "Complete the assigned workflow task", backstory: "Careful, clear, and evidence-led", model: textValue(c.model, "openai/gpt-4.1-mini"), skill_ids: configList(c.skill_ids), tool_ids: configList(c.tool_ids) }];
      const taskLines = (c.tasks ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
      const schema = c.output_schema || "NEXUSTaskOutput";
      const tasksUnchanged = taskMetadata.length > 0 && c.tasks === c.tasks_source;
      const agentIds = new Set(agents.map((agent) => String(agent.id)));
      const tasks: JsonRecord[] = tasksUnchanged
        ? taskMetadata.map((meta, index) => ({ ...meta, id: String(meta.id ?? `task_${index + 1}`), agent_id: agentIds.has(String(meta.agent_id)) ? String(meta.agent_id) : agents[Math.min(index, agents.length - 1)].id, description: String(meta.description ?? ""), expected_output: String(meta.expected_output ?? "A clear, structured result"), output_schema: String(meta.output_schema ?? schema) }))
        : (taskLines.length ? taskLines : ["Complete the request and return a concise result."]).map((description, index) => ({ id: `task_${index + 1}`, agent_id: agents[Math.min(index, agents.length - 1)].id, description, expected_output: String(taskMetadata[index]?.expected_output ?? "A clear, structured result"), output_schema: String(taskMetadata[index]?.output_schema ?? schema), ...(taskMetadata[index]?.output_schema_json ? { output_schema_json: taskMetadata[index].output_schema_json } : {}), ...(taskMetadata[index]?.expected_artifact_paths ? { expected_artifact_paths: taskMetadata[index].expected_artifact_paths } : {}) }));
      const hierarchical = c.process === "hierarchical" && Boolean(c.manager_agent_id) && agentIds.has(c.manager_agent_id);
      const taskIds = new Set(tasks.map((task) => String(task.id)));
      for (const task of tasks) if (Array.isArray(task.context_task_ids)) task.context_task_ids = (task.context_task_ids as unknown[]).filter((id) => taskIds.has(String(id)));
      return { id: node.id, kind: "crew", label: node.data.label, agents, tasks, process: hierarchical ? "hierarchical" : "sequential", ...(hierarchical ? { manager_agent_id: c.manager_agent_id } : {}), consensus_config: consensusConfig(c), ...contractFields(c) };
    }
    if (node.type === "autogen") return { id: node.id, kind: "sandbox", label: node.data.label, coder_model: textValue(c.coder_agent, "openai/gpt-4.1-mini"), reviewer_model: textValue(c.reviewer_agent, "openai/gpt-4.1-mini"), coder_instructions: c.coder_instructions ?? "", reviewer_instructions: c.reviewer_instructions ?? "", sandbox_provider: c.sandbox_provider || "docker", max_rounds: Number(c.max_turns || 8), timeout_seconds: Number(c.timeout_seconds || 900), verification_command: c.verification_command || "python -m compileall .", skill_ids: configList(c.skill_ids), tool_ids: configList(c.tool_ids), consensus_config: consensusConfig(c), ...contractFields(c) };
    if (node.type === "approval") return { id: node.id, kind: "approval", label: node.data.label, action_description: textValue(c.message, node.data.description), boundary_rules: (c.boundary_rules ?? "").split(/[\n,]/).map((rule) => rule.trim()).filter(Boolean), required_role: "admin", timeout_seconds: 86400 };
    if (node.type === "router") {
      const parsedRules = (c.rules ?? "").split("\n").map((line) => line.trim()).filter(Boolean).map((line, index) => {
        const [condition = "", routeName = `route_${index + 1}`] = line.split("→").map((part) => part.trim());
        const match = condition.match(/^([\w.]+)\s*(==|!=|>=|<=|>|<|exists)\s*(.*)$/);
        const raw = match?.[3]?.replace(/^['"]|['"]$/g, "") ?? "true";
        let value: string | number | boolean = raw;
        if (raw === "true" || raw === "false") value = raw === "true";
        else if (raw !== "" && Number.isFinite(Number(raw))) value = Number(raw);
        return { name: routeName.replace(/[^a-zA-Z0-9_-]/g, "_") || `route_${index + 1}`, field_path: match?.[1] ?? textValue(c.field, "result.approved"), operator: OPERATOR_CODES[match?.[2] ?? "=="] ?? "eq", value };
      });
      let preserved: JsonRecord[] = [];
      try { preserved = JSON.parse(c.routes_json ?? "[]") as JsonRecord[]; } catch { preserved = []; }
      const routes = preserved.length && c.rules === c.rules_source ? preserved : parsedRules.length ? parsedRules : [{ name: "approved", field_path: textValue(c.field, "result.approved"), operator: "eq", value: true }];
      return { id: node.id, kind: "router", label: node.data.label, routes, default_route: c.default_route || "otherwise", artifact_gate: c.artifact_gate === "true", max_loop_iterations: Number(c.max_loop_iterations || 0) };
    }
    const baseId = (c.knowledge_base_ids ?? "").split("\n").map((entry) => entry.trim()).find(Boolean);
    return { id: node.id, kind: "rag", label: node.data.label, knowledge_base_id: baseId || "00000000-0000-4000-8000-000000000001", mcp_server_ids: (c.mcp_servers ?? "").split("\n").map((server) => server.trim()).filter(Boolean), query_template: "{input}", top_k: Number(c.top_k || 5) };
  });
  const edgeIndexes = new Map<string, number>();
  const sourceAgentId = (nodeId: string) => { const node = nodes.find((candidate) => candidate.id === nodeId); return node?.type === "crew" ? `${node.id}_agent_1` : node?.type === "autogen" ? `${node.id}_coder` : null; };
  const targetAgentId = (nodeId: string) => nodes.some((node) => node.id === nodeId && node.type === "crew") ? `${nodeId}_agent_1` : null;
  const learning_edges = edges.filter((edge) => edge.data?.learning === true).map((edge) => ({ source_agent_id: sourceAgentId(edge.source), target_agent_id: targetAgentId(edge.target), scope: learning.scope, allow_heuristics: learning.allowHeuristics, allow_code_patterns: learning.allowCodePatterns, require_human_approval: learning.requireApproval })).filter((edge) => edge.source_agent_id && edge.target_agent_id);
  return { id: workflowId, tenant_id: scope.tenant_id, workspace_id: scope.workspace_id, name, version: 1, nodes: mapped, layout: Object.fromEntries(nodes.map((node) => [node.id, node.position])), learning_edges, ...(modes ? { modes } : {}), edges: edges.filter((edge) => edge.data?.learning !== true).map((edge) => {
    const sourceNode = nodes.find((node) => node.id === edge.source);
    const loop = edge.data?.loop_back === true ? { loop_back: true } : {};
    if (sourceNode?.type !== "router") return { source: edge.source, target: edge.target, ...loop };
    const router = mapped.find((node) => node.id === edge.source) as { routes: Array<{ name: string }>; default_route: string };
    if (typeof edge.data?.route === "string") return { source: edge.source, target: edge.target, route: edge.data.route, ...loop };
    const index = edgeIndexes.get(edge.source) ?? 0; edgeIndexes.set(edge.source, index + 1);
    return { source: edge.source, target: edge.target, route: router.routes[index]?.name ?? router.default_route, ...loop };
  }) };
}

function specToCanvas(spec: JsonRecord): { nodes: StudioNode[]; edges: Edge[]; learningConfig: { scope: string; allowHeuristics: boolean; allowCodePatterns: boolean; requireApproval: boolean }; modes?: JsonRecord } {
  const rawNodes = Array.isArray(spec.nodes) ? spec.nodes as JsonRecord[] : [];
  const savedLayout = spec.layout && typeof spec.layout === "object" ? spec.layout as Record<string, JsonRecord> : {};
  const nodes: StudioNode[] = rawNodes.map((raw, index) => {
    const kind = raw.kind === "sandbox" ? "autogen" : raw.kind as CanvasKind;
    const savedPosition = savedLayout[String(raw.id)];
    const position = savedPosition && typeof savedPosition.x === "number" && typeof savedPosition.y === "number"
      ? { x: savedPosition.x, y: savedPosition.y }
      : { x: 80 + (index % 3) * 350, y: 80 + Math.floor(index / 3) * 230 };
    const config: Record<string, string> = {};
    if (kind === "start") Object.assign(config, { trigger_type: String(raw.trigger_type ?? "manual"), input_schema: JSON.stringify(raw.input_schema ?? {}, null, 2), schedule: String(raw.schedule ?? "") });
    if (kind === "crew") {
      const firstAgent = Array.isArray(raw.agents) ? raw.agents[0] as JsonRecord | undefined : undefined;
      config.agents = Array.isArray(raw.agents) ? (raw.agents as JsonRecord[]).map((a) => `${a.role} | ${a.goal} | ${a.backstory ?? ""}`).join("\n") : "";
      config.agent_metadata = JSON.stringify(raw.agents ?? []);
      config.tasks = Array.isArray(raw.tasks) ? (raw.tasks as JsonRecord[]).map((t) => String(t.description ?? "")).join("\n") : "";
      config.task_metadata = JSON.stringify(raw.tasks ?? []);
      config.model = String((Array.isArray(raw.agents) && (raw.agents[0] as JsonRecord | undefined)?.model) ?? "");
      config.skill_ids = Array.isArray(firstAgent?.skill_ids) ? firstAgent.skill_ids.join("\n") : "";
      config.tool_ids = Array.isArray(firstAgent?.tool_ids) ? firstAgent.tool_ids.join("\n") : "";
      config.output_schema = String((Array.isArray(raw.tasks) && (raw.tasks[0] as JsonRecord | undefined)?.output_schema) ?? "");
      Object.assign(config, { process: String(raw.process ?? "sequential"), manager_agent_id: String(raw.manager_agent_id ?? ""), join: String(raw.join ?? "any"), expected_artifact_paths: JSON.stringify(raw.expected_artifact_paths ?? []), requires_visual_evidence: String(Boolean(raw.requires_visual_evidence)) });
      Object.assign(config, { agents_source: config.agents, tasks_source: config.tasks, skill_ids_source: config.skill_ids, tool_ids_source: config.tool_ids });
      const cc = (raw.consensus_config ?? {}) as JsonRecord; Object.assign(config, { consensus_enabled: String(Boolean(cc.enabled)), consensus_models: Array.isArray(cc.models) ? cc.models.join("\n") : "", arbiter_model: String(cc.arbiter_model ?? ""), consensus_threshold: String(cc.min_agreement_threshold ?? 0.85) });
    }
    if (kind === "autogen") Object.assign(config, { coder_agent: String(raw.coder_model ?? ""), reviewer_agent: String(raw.reviewer_model ?? ""), coder_instructions: String(raw.coder_instructions ?? ""), reviewer_instructions: String(raw.reviewer_instructions ?? ""), sandbox_provider: String(raw.sandbox_provider ?? "docker"), timeout_seconds: String(raw.timeout_seconds ?? 900), max_turns: String(raw.max_rounds ?? 8), skill_ids: Array.isArray(raw.skill_ids) ? raw.skill_ids.join("\n") : "", tool_ids: Array.isArray(raw.tool_ids) ? raw.tool_ids.join("\n") : "", verification_command: String(raw.verification_command ?? ""), join: String(raw.join ?? "any"), expected_artifact_paths: JSON.stringify(raw.expected_artifact_paths ?? []), requires_visual_evidence: String(Boolean(raw.requires_visual_evidence)) });
    if (kind === "autogen") { const cc = (raw.consensus_config ?? {}) as JsonRecord; Object.assign(config, { consensus_enabled: String(Boolean(cc.enabled)), consensus_models: Array.isArray(cc.models) ? cc.models.join("\n") : "", arbiter_model: String(cc.arbiter_model ?? ""), consensus_threshold: String(cc.min_agreement_threshold ?? 0.85) }); }
    if (kind === "approval") Object.assign(config, { message: String(raw.action_description ?? ""), boundary_rules: Array.isArray(raw.boundary_rules) ? raw.boundary_rules.join("\n") : "" });
    if (kind === "router") {
      const readable = routesToText(raw.routes);
      Object.assign(config, { field: String(((raw.routes as JsonRecord[] | undefined)?.[0])?.field_path ?? ""), rules: readable, rules_source: readable, routes_json: JSON.stringify(raw.routes ?? []), default_route: String(raw.default_route ?? "otherwise"), artifact_gate: String(Boolean(raw.artifact_gate)), max_loop_iterations: String(raw.max_loop_iterations ?? 0) });
    }
    if (kind === "rag") Object.assign(config, { knowledge_base_ids: String(raw.knowledge_base_id ?? ""), mcp_servers: Array.isArray(raw.mcp_server_ids) ? raw.mcp_server_ids.join("\n") : "", top_k: String(raw.top_k ?? 5) });
    return { id: String(raw.id ?? `node-${index}`), type: kind, position, data: { label: String(raw.label ?? kindMeta[kind].label), description: kindMeta[kind].description, config } };
  });
  const rawEdges = Array.isArray(spec.edges) ? spec.edges as JsonRecord[] : [];
  const edges = rawEdges.map((edge, index): Edge => ({
    id: `e-${index}-${String(edge.source)}-${String(edge.target)}`, source: String(edge.source), target: String(edge.target),
    data: edge.route || edge.loop_back ? { ...(edge.route ? { route: edge.route } : {}), ...(edge.loop_back ? { loop_back: true } : {}) } : undefined,
    ...(edge.loop_back ? { label: "rework", labelStyle: { fontSize: 10, fill: "#d9a441" }, style: { stroke: "#d9a441", strokeWidth: 1.4, strokeDasharray: "4 4" } } : { style: { stroke: "#a9b8ad", strokeWidth: 1.6 } }),
  }));
  const agentToNode = new Map<string, string>();
  for (const raw of rawNodes) {
    if (raw.kind === "crew" && Array.isArray(raw.agents)) for (const agent of raw.agents as JsonRecord[]) agentToNode.set(String(agent.id), String(raw.id));
    if (raw.kind === "sandbox") agentToNode.set(`${String(raw.id)}_coder`, String(raw.id));
  }
  const savedLearning = Array.isArray(spec.learning_edges) ? spec.learning_edges as JsonRecord[] : [];
  for (const [index, edge] of savedLearning.entries()) {
    const source = agentToNode.get(String(edge.source_agent_id)); const target = agentToNode.get(String(edge.target_agent_id));
    if (source && target) edges.push({ id: `learning-${index}-${source}-${target}`, source, target, data: { learning: true, scope: edge.scope, allow_heuristics: edge.allow_heuristics, allow_code_patterns: edge.allow_code_patterns, require_human_approval: edge.require_human_approval }, style: { stroke: "#7776c8", strokeWidth: 2, strokeDasharray: "7 5" } });
  }
  const firstLearning = savedLearning[0];
  const modes = spec.modes && typeof spec.modes === "object" ? spec.modes as JsonRecord : undefined;
  return { nodes, edges, modes, learningConfig: firstLearning ? { scope: String(firstLearning.scope ?? "CREW_LOCAL"), allowHeuristics: Boolean(firstLearning.allow_heuristics), allowCodePatterns: Boolean(firstLearning.allow_code_patterns), requireApproval: Boolean(firstLearning.require_human_approval) } : { scope: "CREW_LOCAL", allowHeuristics: true, allowCodePatterns: false, requireApproval: false } };
}

function WorkflowStudioInner({ embedded = false, token, scope: currentScope, activeNodeId, openWorkflowId, approvals = [], onApprovalResolved, onRun, onModal }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<StudioNode>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [draftSpecId, setDraftSpecId] = useState<string | null>(null);
  const [savedWorkflows, setSavedWorkflows] = useState<SavedWorkflow[]>([]);
  const [recentRuns, setRecentRuns] = useState<RunHistory[]>([]);
  const [historyRunId, setHistoryRunId] = useState("");
  const [name, setName] = useState("Untitled workflow");
  const [scopeText, setScopeText] = useState(JSON.stringify(currentScope));
  const [runInput, setRunInput] = useState('{\n  "task": "Review the supplied workflow request"\n}');
  const taskText = useMemo(() => {
    try { const parsed: unknown = JSON.parse(runInput); return parsed && typeof parsed === "object" && !Array.isArray(parsed) && typeof (parsed as Record<string, unknown>).task === "string" ? String((parsed as Record<string, unknown>).task) : ""; }
    catch { return ""; }
  }, [runInput]);
  const updateTask = (value: string) => {
    let current: Record<string, unknown> = {};
    try { const parsed: unknown = JSON.parse(runInput); if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) current = parsed as Record<string, unknown>; } catch { /* Invalid JSON is replaced by the typed request. */ }
    setRunInput(JSON.stringify({ ...current, task: value }, null, 2));
  };
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [learningMode, setLearningMode] = useState(false);
  const [learningConfig, setLearningConfig] = useState({ scope: "CREW_LOCAL", allowHeuristics: true, allowCodePatterns: false, requireApproval: false });
  const [modes, setModes] = useState<JsonRecord | undefined>(undefined);
  const [lineage, setLineage] = useState<Lineage | null>(null);
  const [evolutionOpen, setEvolutionOpen] = useState(false);
  const [evolveNonce, setEvolveNonce] = useState(0);
  const [overlay, setOverlay] = useState<{ version: number; statuses: Record<string, DiffStatus>; proposal: boolean } | null>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const inputFileRef = useRef<HTMLInputElement>(null);
  const flowInstance = useRef<ReactFlowInstance<StudioNode, Edge> | null>(null);
  const selected = nodes.find((node) => node.id === selectedId);
  const activeApproval = approvals.find((approval) => approval.node_id === selectedId) ?? approvals.find((approval) => nodes.some((node) => node.type === "approval" && node.id === approval.node_id));
  const scope = useMemo(() => {
    try { return JSON.parse(scopeText) as { tenant_id: string; workspace_id: string }; }
    catch { return { tenant_id: "00000000-0000-4000-8000-000000000001", workspace_id: "00000000-0000-4000-8000-000000000001" }; }
  }, [scopeText]);
  useEffect(() => { if (currentScope.tenant_id && currentScope.workspace_id) setScopeText(JSON.stringify(currentScope)); }, [currentScope]);
  useEffect(() => { if (token) setMessage((current) => current.startsWith("Connect a workspace") ? "" : current); }, [token]);
  useEffect(() => {
    if (!token) { setSavedWorkflows([]); return; }
    let stopped = false;
    void apiRequest<SavedWorkflow[]>("/api/v1/workflows", token).then((workflows) => { if (!stopped) setSavedWorkflows(workflows); }).catch(() => undefined);
    return () => { stopped = true; };
  }, [token]);
  useEffect(() => {
    if (!token || !workflowId) { setRecentRuns([]); return; }
    let stopped = false;
    const refresh = async () => {
      try { const rows = await apiRequest<RunHistory[]>(`/api/v1/runs?workflow_id=${workflowId}`, token); if (!stopped) setRecentRuns(rows); }
      catch { if (!stopped) setRecentRuns([]); }
    };
    void refresh(); const timer = window.setInterval(() => void refresh(), 10000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [token, workflowId]);

  const refreshLineage = useCallback(async () => {
    if (!token || !workflowId) { setLineage(null); return; }
    try { setLineage(await apiRequest<Lineage>(`/api/v1/workflows/${workflowId}/generations?create=${evolutionOpen ? "true" : "false"}`, token)); }
    catch { setLineage(null); }
  }, [evolutionOpen, token, workflowId]);
  useEffect(() => { void refreshLineage(); }, [refreshLineage]);

  const connect = useCallback((connection: Connection) => {
    const source = nodes.find((node) => node.id === connection.source); const target = nodes.find((node) => node.id === connection.target);
    if (learningMode && !(["crew", "autogen"].includes(String(source?.type)) && target?.type === "crew")) { setMessage("Learning edges connect a Crew or sandbox coder to a Crew target."); return; }
    setEdges((current) => addEdge({ ...connection, id: identifier(), data: learningMode ? { learning: true } : undefined, style: learningMode ? { stroke: "#7776c8", strokeWidth: 2, strokeDasharray: "7 5" } : { stroke: "#a9b8ad", strokeWidth: 1.6 } }, current));
  }, [learningMode, nodes, setEdges]);
  const changeSelected = (data: StudioNodeData) => setNodes((current) => current.map((node) => node.id === selectedId ? { ...node, data } : node));
  const openWorkflow = useCallback(async (id: string) => {
    if (!id || !token) return;
    setOverlay(null);
    try {
      const spec = await apiRequest<JsonRecord>(`/api/v1/workflows/${id}`, token);
      const canvas = specToCanvas(spec);
      setNodes(canvas.nodes); setEdges(canvas.edges); setLearningConfig(canvas.learningConfig); setModes(canvas.modes); setName(String(spec.name ?? "Untitled workflow")); setWorkflowId(id); setSelectedId(embedded ? null : canvas.nodes.find((node) => node.type === "autogen")?.id ?? canvas.nodes[0]?.id ?? null);
      setDraftSpecId(null);
      setMessage("Workflow opened from this workspace.");
    } catch (error) { setMessage(readError(error)); }
  }, [embedded, setEdges, setNodes, token]);
  useEffect(() => { if (openWorkflowId) void openWorkflow(openWorkflowId); }, [openWorkflow, openWorkflowId]);
  const previewGeneration = async (generation: Generation) => {
    if (!token || !workflowId) return;
    try {
      const detail = await apiRequest<Generation & { spec: JsonRecord; parent_spec: JsonRecord | null }>(`/api/v1/workflows/${workflowId}/generations/${generation.version}`, token);
      const canvas = specToCanvas(detail.spec);
      const parent = detail.parent_spec ? specToCanvas(detail.parent_spec) : null;
      const removed = new Set(detail.diff.removed_nodes ?? []);
      const lowest = Math.max(0, ...canvas.nodes.map((node) => node.position.y));
      const ghostNodes = parent ? parent.nodes.filter((node) => removed.has(node.id)).map((node, index) => ({ ...node, position: { x: 60 + index * 360, y: lowest + 380 }, draggable: false })) : [];
      const ghostEdges = parent ? parent.edges.filter((edge) => removed.has(edge.source) || removed.has(edge.target)).map((edge) => ({ ...edge, id: `ghost-${edge.id}`, style: { stroke: "#fb7185", strokeWidth: 1.6, strokeDasharray: "5 4" } })) : [];
      setNodes([...canvas.nodes, ...ghostNodes]); setEdges([...canvas.edges, ...ghostEdges]); setModes(canvas.modes); setLearningConfig(canvas.learningConfig);
      setOverlay({ version: generation.version, statuses: diffStatuses(detail.diff), proposal: detail.status === "proposed" });
      setSelectedId(null);
      setMessage(`Previewing team generation v${generation.version}. Green is new, amber is changed, rose is pruned.`);
      window.setTimeout(() => void flowInstance.current?.fitView({ padding: 0.08, duration: 200, maxZoom: 1.05 }), 120);
    } catch (error) { setMessage(readError(error)); }
  };
  const afterEvolutionChange = async (activeId?: string) => {
    if (activeId) await openWorkflow(activeId);
    else if (overlay) { setOverlay(null); if (workflowId) await openWorkflow(workflowId); }
    await refreshLineage();
  };
  const newDraft = () => { setNodes(initialNodes); setEdges(initialEdges); setModes(undefined); setLearningConfig({ scope: "CREW_LOCAL", allowHeuristics: true, allowCodePatterns: false, requireApproval: false }); setName("Untitled workflow"); setWorkflowId(null); setDraftSpecId(null); setSelectedId(null); setMessage("New workflow draft."); };

  const applyArchitectSpec = async (spec: JsonRecord) => {
    const canvas = specToCanvas(spec);
    setNodes([]); setEdges([]);
    for (const node of canvas.nodes) {
      await new Promise((resolve) => window.setTimeout(resolve, 95));
      setNodes((current) => [...current, node]);
    }
    setEdges(canvas.edges); setLearningConfig(canvas.learningConfig); setModes(canvas.modes);
    setName(String(spec.name ?? "AI-generated workflow")); setDraftSpecId(String(spec.id ?? identifier()));
    setWorkflowId(null); setSelectedId(null); setMessage("AI workflow applied to the canvas. Review the steps, then save.");
  };

  const currentArchitectSpec = workflowId
    ? makeSpec(nodes, edges, scope, workflowId, name, learningConfig, modes)
    : undefined;
  const addNode = (kind: CanvasKind) => {
    if (kind === "start" && nodes.some((node) => node.type === "start")) { setMessage("A workflow can have only one start trigger."); return; }
    const nodeId = `${kind}-${identifier().slice(0, 8)}`;
    const node: StudioNode = { id: nodeId, type: kind, position: { x: 250 + Math.random() * 300, y: 110 + Math.random() * 320 }, data: { label: kindMeta[kind].label, description: kindMeta[kind].description, config: {} } };
    setNodes((current) => [...current, node]);
    setSelectedId(nodeId);
  };

  const save = async (): Promise<JsonRecord | null> => {
    if (!token) { setMessage("Connect a workspace (top right) to save and run workflows."); return null; }
    setBusy(true);
    try {
      const spec = makeSpec(nodes, edges, scope, workflowId ?? draftSpecId ?? identifier(), name, learningConfig, modes);
      await apiRequest("/api/v1/workflows/validate", token, { method: "POST", body: JSON.stringify(spec) });
      const saved = workflowId
        ? await apiRequest<JsonRecord>(`/api/v1/workflows/${workflowId}`, token, { method: "PUT", body: JSON.stringify(spec) })
        : await apiRequest<JsonRecord>("/api/v1/workflows", token, { method: "POST", body: JSON.stringify(spec) });
      const id = String(saved.id ?? spec.id);
      setWorkflowId(id);
      setSavedWorkflows((current) => current.some((workflow) => workflow.id === id) ? current.map((workflow) => workflow.id === id ? { id, name, version: Number(saved.version ?? 1) } : workflow) : [...current, { id, name, version: Number(saved.version ?? 1) }]);
      setMessage("Workflow saved to this workspace.");
      return { ...spec, ...saved, id };
    } catch (error) {
      setMessage(error instanceof ApiError && error.status === 409 && !workflowId
        ? `A workflow named “${name}” already exists in this workspace. Rename this one, or pick the saved one from “Open workflow…”.`
        : readError(error));
      return null;
    }
    finally { setBusy(false); }
  };

  const run = async () => {
    const saved = await save();
    if (!saved || !token) return;
    let inputData: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(runInput);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Run input must be a JSON object.");
      inputData = parsed as Record<string, unknown>;
      if (new TextEncoder().encode(JSON.stringify(inputData)).byteLength > 1_048_576) throw new Error("Run input exceeds the 1 MiB API limit.");
    } catch (error) { setMessage(readError(error)); return; }
    setBusy(true);
    try {
      const result = await apiRequest<WorkflowEnvelope>(`/api/v1/workflows/${String(saved.id)}/runs`, token, { method: "POST", body: JSON.stringify({ input_data: inputData }) });
      onRun({ workflowId: String(saved.id), runId: result.run_id ?? result.id });
      setMessage("Run queued. The inspector is listening for live events.");
    } catch (error) { setMessage(readError(error)); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    const handleRunShortcut = () => { void run(); };
    window.addEventListener("nexus:run", handleRunShortcut);
    return () => window.removeEventListener("nexus:run", handleRunShortcut);
  });
  useEffect(() => {
    const applyViewport = (width: number) => {
      const instance = flowInstance.current;
      if (!instance) return;
      void instance.fitView({ padding: width < 600 ? 0.12 : 0.06, duration: 180, maxZoom: 1.05 });
    };
    const resize = () => { window.setTimeout(() => applyViewport(window.innerWidth), 250); };
    window.addEventListener("resize", resize);
    const wrap = document.querySelector(".reactflow-wrap");
    const observer = wrap ? new ResizeObserver((entries) => { const width = entries[0]?.contentRect.width; if (width) applyViewport(width); }) : null;
    if (wrap && observer) observer.observe(wrap);
    return () => { window.removeEventListener("resize", resize); observer?.disconnect(); };
  }, []);

  const attachRunFile = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 1_048_576) throw new Error("This file exceeds the 1 MiB API run-input limit.");
      const current = JSON.parse(runInput) as Record<string, unknown>;
      if (file.name.toLowerCase().endsWith(".csv")) {
        current.dataset = await file.text();
      } else if (file.name.toLowerCase().endsWith(".xlsx")) {
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Could not read this workbook."));
          reader.onload = () => typeof reader.result === "string" ? resolve(reader.result) : reject(new Error("Workbook encoding failed."));
          reader.readAsDataURL(file);
        });
        current.dataset_base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
      } else {
        const extension = file.name.toLowerCase().split(".").pop() ?? "";
        if (!["py", "js", "ts", "json", "yaml", "yml", "md", "txt", "toml", "html", "css"].includes(extension)) throw new Error("Choose a CSV, XLSX, or source/document file.");
        const sandboxFiles = current.sandbox_files && typeof current.sandbox_files === "object" ? current.sandbox_files as Record<string, string> : {};
        sandboxFiles[file.name] = await file.text();
        current.sandbox_files = sandboxFiles;
      }
      current.filename = file.name;
      current.task = `Analyze ${file.name}. Validate the data, calculate metrics for the question, and create charts.`;
      const encoded = JSON.stringify(current);
      if (new TextEncoder().encode(encoded).byteLength > 1_000_000) throw new Error("This file is too large for the 1 MiB run-input limit.");
      setRunInput(JSON.stringify(current, null, 2));
      setMessage(`${file.name} added to the run input. Review the JSON, then start the workflow.`);
    } catch (error) { setMessage(readError(error)); }
    finally { if (inputFileRef.current) inputFileRef.current.value = ""; }
  };

  const exportWorkflow = async (format: "json" | "yaml") => {
    const spec = makeSpec(nodes, edges, scope, workflowId ?? identifier(), name, learningConfig, modes);
    try {
      if (workflowId && token) {
        const response = await fetch(`/api/v1/workflows/${workflowId}/export?file_format=${format}`, { headers: { authorization: `Bearer ${token}` } });
        if (response.ok) { downloadFile(`${name.replace(/\W+/g, "-").toLowerCase()}.${format}`, await response.text(), format === "json" ? "application/json" : "application/yaml"); return; }
      }
      const content = format === "json" ? JSON.stringify(spec, null, 2) : toYaml(spec);
      downloadFile(`${name.replace(/\W+/g, "-").toLowerCase()}.${format}`, content, format === "json" ? "application/json" : "application/yaml");
    } catch (error) { setMessage(readError(error)); }
  };

  const importWorkflow = async (file?: File) => {
    if (!file) return;
    try {
      const content = await file.text();
      const isYaml = file.name.endsWith(".yaml") || file.name.endsWith(".yml");
      let spec: JsonRecord;
      if (isYaml) {
        if (!token) throw new Error("Connect a workspace to import YAML workflow files.");
        spec = await apiRequest<JsonRecord>("/api/v1/workflows/import?file_format=yaml", token, { method: "POST", headers: { "content-type": "application/octet-stream" }, body: content });
      } else spec = JSON.parse(content) as JsonRecord;
      const canvas = specToCanvas(spec);
      setNodes(canvas.nodes); setEdges(canvas.edges); setLearningConfig(canvas.learningConfig); setModes(canvas.modes); setName(String(spec.name ?? "Imported workflow"));
      if (typeof spec.id === "string") setWorkflowId(spec.id);
      const json = prompt("Workspace scope JSON (tenant_id and workspace_id)", JSON.stringify({ tenant_id: scope.tenant_id, workspace_id: scope.workspace_id }));
      if (json) { const importedScope = JSON.parse(json) as { tenant_id: string; workspace_id: string }; setScopeText(JSON.stringify(importedScope)); spec = { ...spec, ...importedScope }; }
      if (token && !isYaml) {
        const saved = await apiRequest<JsonRecord>("/api/v1/workflows/import?file_format=json", token, { method: "POST", headers: { "content-type": "application/octet-stream" }, body: JSON.stringify(spec) });
        if (saved.id) { setWorkflowId(String(saved.id)); setSavedWorkflows((current) => [...current, { id: String(saved.id), name: String(saved.name ?? "Imported workflow"), version: Number(saved.version ?? 1) }]); }
      }
      setMessage("Workflow imported. Review its workspace scope and node settings before running.");
    } catch (error) { setMessage(`Could not import this workflow: ${readError(error)}`); }
  };

  return (
    <div className="studio-layout">
      <section className="canvas-panel">
        <header className="canvas-toolbar">
          <div className="workflow-title"><h1>Workflow Studio</h1><label className="crumb" htmlFor="workflow-name">WORKFLOW <span>/</span> DRAFT</label><input id="workflow-name" aria-label="Workflow name" value={name} onChange={(event) => setName(event.target.value)} /></div>
          <div className="toolbar-actions"><select aria-label="Open saved workflow" className="saved-workflow-picker" value={workflowId ?? ""} onChange={(event) => void openWorkflow(event.target.value)}><option value="">Open workflow…</option>{savedWorkflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name} · v{workflow.version}</option>)}</select>{workflowId && <div className="evolution-toolbar">{lineage && lineage.generations.length > 1 && <select aria-label="Team generations" value={lineage.generations.find((generation) => generation.workflow_id === workflowId)?.version ?? ""} onChange={(event) => { const generation = lineage.generations.find((item) => item.version === Number(event.target.value)); if (!generation) return; if (generation.status === "proposed") void previewGeneration(generation); else void openWorkflow(generation.workflow_id); }}>{lineage.generations.map((generation) => <option key={generation.version} value={generation.version}>v{generation.version} · {generation.status === "proposed" ? "proposal" : generation.status.replace("_", " ")}{generation.fitness !== null ? ` · ${Math.round(generation.fitness * 100)}%` : ""}</option>)}</select>}<button className="button button-quiet" onClick={() => { setSelectedId(null); setEvolutionOpen(true); setEvolveNonce((value) => value + 1); }}>Evolve Team Topology</button><button className="button button-quiet" aria-pressed={evolutionOpen} onClick={() => { setSelectedId(null); setEvolutionOpen((open) => !open); }}>{lineage && lineage.generations.length > 1 ? `Generations (${lineage.lineage})` : "Generations"}</button></div>}<button className="button button-quiet" onClick={() => newDraft()}>New</button><button className="button button-primary" disabled={busy || overlay !== null} onClick={() => void save()}>{busy ? "Saving…" : "Save workflow"}</button></div>
        </header>
        {!embedded && <form className="request-bar" onSubmit={(event) => { event.preventDefault(); void run(); }}>
          <label htmlFor="workflow-request">Request</label>
          <input id="workflow-request" value={taskText} onChange={(event) => updateTask(event.target.value)} placeholder="Describe what you want this team to do, then press Enter to run…" />
          <button className="button button-primary button-small" type="submit" disabled={busy || overlay !== null}>{busy ? "Working…" : "Send & run"}</button>
        </form>}
        {overlay && <div className="preview-banner" role="status"><strong>Previewing team generation v{overlay.version}</strong><span className="preview-banner__legend"><span><i style={{ background: "#34d399" }} />New</span><span><i style={{ background: "#f59e0b" }} />Changed</span><span><i style={{ background: "#fb7185" }} />Pruned</span></span><button className="button button-small" onClick={() => void afterEvolutionChange()}>Exit preview</button></div>}
        <details className="run-history"><summary>Run History · {recentRuns.length} recent runs</summary><div className="run-history-list">{recentRuns.map((item) => <button key={item.id} className="button button-small" onClick={() => { setHistoryRunId(item.id); onRun({ workflowId: item.workflow_id, runId: item.id }); }}>{new Date(item.created_at).toLocaleString()} · {item.status} · {item.artifacts.length} files</button>)}</div>{historyRunId && <RunArtifactGallery runId={historyRunId} token={token} />}</details>
        <input ref={importRef} className="sr-only" type="file" accept=".json,.yaml,.yml" onChange={(event) => void importWorkflow(event.target.files?.[0])} />
        <section className="canvas-stage" aria-label="Workflow canvas">
        <div className="canvas-subbar"><div className="canvas-subbar__scope"><span className="live-indicator" />{scope.workspace_id ? `Workspace ${scope.workspace_id.slice(0, 8)}` : "Local preview"}</div><div className="subbar-right"><button className={`button button-small ${learningMode ? "learning-mode-active" : ""}`} onClick={() => setLearningMode((active) => !active)} title="Connect agents with a scoped learning edge">{learningMode ? "Learning edges: on" : "Learning edges"}</button><button className="button button-small" onClick={() => onModal("api-key")}>API key</button><button className="button button-small" onClick={() => onModal("widget")}>Embed</button></div></div>
          {learningMode && <div className="learning-edge-controls"><label>Scope<select value={learningConfig.scope} onChange={(event) => setLearningConfig((current) => ({ ...current, scope: event.target.value }))}><option value="CREW_LOCAL">Crew local</option><option value="WORKFLOW_SCOPED">Workflow scoped</option><option value="WORKSPACE_QUARANTINE">Workspace quarantine</option><option value="WORKSPACE_VERIFIED">Workspace verified</option></select></label><label><input type="checkbox" checked={learningConfig.allowHeuristics} onChange={(event) => setLearningConfig((current) => ({ ...current, allowHeuristics: event.target.checked }))} /> Allow heuristics</label><label><input type="checkbox" checked={learningConfig.allowCodePatterns} onChange={(event) => setLearningConfig((current) => ({ ...current, allowCodePatterns: event.target.checked }))} /> Allow code patterns</label><label><input type="checkbox" checked={learningConfig.requireApproval} onChange={(event) => setLearningConfig((current) => ({ ...current, requireApproval: event.target.checked }))} /> Require human approval</label><span>Connect a Crew or sandbox coder to a Crew target.</span></div>}
        {nodes.length === 0 && <div className="canvas-empty" role="status"><strong>No team yet</strong><span>{embedded ? "Describe a task in the Agent Composer. The generated team appears here." : "Describe a task to generate a team, or add nodes from the dock."}</span></div>}
        <div className="reactflow-wrap"><ReactFlow<StudioNode, Edge> onInit={(instance) => { flowInstance.current = instance; if (window.innerWidth < 600) { setSelectedId(null); setNodes((current) => current.map((node, index) => ({ ...node, position: { x: 38, y: 30 + index * 188 }, sourcePosition: Position.Bottom, targetPosition: Position.Top }))); } window.setTimeout(() => void instance.fitView({ padding: 0.06, duration: 180, maxZoom: 1.05 }), 260); }} fitView fitViewOptions={{ padding: 0.06, maxZoom: 1.05 }} nodes={nodes.map((node) => {
          const approval = approvals.find((item) => item.node_id === node.id);
          return { ...node, data: { ...node.data, diff: overlay?.statuses[node.id], active: node.id === activeNodeId, status: node.id === activeNodeId ? "RUNNING" : approval ? "WAITING_APPROVAL" : node.data.status, approvalId: approval?.approval_id, token, onApprovalResolved } };
        })} edges={edges.map((edge) => edge.data?.learning === true ? edge : ({ ...edge, animated: Boolean(activeNodeId && (edge.source === activeNodeId || edge.target === activeNodeId)), className: activeNodeId && (edge.source === activeNodeId || edge.target === activeNodeId) ? "execution-edge-active" : "execution-edge" }))} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={connect} onNodeClick={(_, node) => setSelectedId(node.id)} onPaneClick={() => setSelectedId(null)} minZoom={0.16} maxZoom={1.5} proOptions={{ hideAttribution: true }}><Background color="var(--canvas-grid-dot)" gap={22} size={1} variant={BackgroundVariant.Dots} /></ReactFlow></div>
        {evolutionOpen && workflowId && <TeamEvolutionPanel token={token} workflowId={workflowId} lineage={lineage} evolveNonce={evolveNonce} onChanged={(id) => void afterEvolutionChange(id)} onPreview={(generation) => void previewGeneration(generation)} onOpen={(id) => void openWorkflow(id)} onMessage={setMessage} onClose={() => setEvolutionOpen(false)} />}
        {selected && <ConfigDrawer kind={selected.type as CanvasKind} data={{ ...selected.data, token }} onChange={changeSelected} onClose={() => setSelectedId(null)} />}
        {selected?.type === "approval" && activeApproval && <div className="canvas-approval-overlay"><span>Decision required</span><button onClick={() => void apiRequest(`/api/v1/approvals/${activeApproval.approval_id}/resolve`, token, { method: "POST", body: JSON.stringify({ decision: "allow_once" }) }).then(() => onApprovalResolved?.(activeApproval.approval_id)).catch((error) => setMessage(readError(error)))}>Allow once</button><button onClick={() => void apiRequest(`/api/v1/approvals/${activeApproval.approval_id}/resolve`, token, { method: "POST", body: JSON.stringify({ decision: "deny" }) }).then(() => onApprovalResolved?.(activeApproval.approval_id)).catch((error) => setMessage(readError(error)))}>Deny</button></div>}
        <div className="canvas-dock" aria-label="Canvas tools">
          <div className="dock-node-actions">{(Object.keys(kindMeta) as CanvasKind[]).map((kind) => <button key={kind} className={`dock-add dock-add--${kind}`} title={`Add ${kindMeta[kind].label}`} aria-label={`Add ${kindMeta[kind].label}`} onClick={() => addNode(kind)}><NodeIcon kind={kind} /><small>{kindMeta[kind].label}</small></button>)}</div>
          {!embedded && <div className="dock-architect"><ArchitectCopilot token={token} currentWorkflow={currentArchitectSpec} empty={!workflowId} onApply={(spec) => void applyArchitectSpec(spec)} onRunGenerated={(spec, runId) => { void openWorkflow(String(spec.id)); onRun({ workflowId: String(spec.id), runId }); }} onUndo={(spec) => {
          if (spec) void applyArchitectSpec(spec);
          else {
            setNodes(initialNodes); setEdges(initialEdges); setWorkflowId(null); setDraftSpecId(null);
            setSelectedId(null); setName("Untitled workflow");
          }
          }} />
          </div>}
          {!embedded && <details className="dock-run-input"><summary>Run input <span>JSON · files up to 1 MiB</span></summary><div className="workflow-run-input__body"><textarea aria-label="Workflow run input JSON" spellCheck={false} value={runInput} onChange={(event) => setRunInput(event.target.value)} /><div><input ref={inputFileRef} className="sr-only" type="file" accept=".csv,.xlsx,.py,.js,.ts,.json,.yaml,.yml,.md,.txt,.toml,.html,.css" onChange={(event) => void attachRunFile(event.target.files?.[0])} /><button className="button button-small" onClick={() => inputFileRef.current?.click()}>Attach file</button></div></div></details>}
          <div className="dock-transfer-actions"><button className="button button-quiet" onClick={() => importRef.current?.click()}>Import</button><button className="button button-quiet" onClick={() => void exportWorkflow("json")}>Export JSON</button><button className="button button-quiet" onClick={() => void exportWorkflow("yaml")}>YAML</button></div>
          <div className="dock-zoom-actions" aria-label="Canvas zoom controls"><button aria-label="Zoom out" onClick={() => void flowInstance.current?.zoomOut()}>−</button><button aria-label="Zoom in" onClick={() => void flowInstance.current?.zoomIn()}>+</button><button aria-label="Fit workflow to canvas" onClick={() => void flowInstance.current?.fitView({ padding: 0.22, duration: 180 })}>Fit</button></div>
        </div>
        <footer className="canvas-footer"><span>Drag to arrange <b>·</b> Connect handles <b>·</b> Changes apply to the next run</span><button className="button button-small" onClick={() => window.dispatchEvent(new CustomEvent("nexus:open-timeline"))}>Run timeline</button></footer>
        {message && <div className="toast-line" role="status"><span>{message}</span><button onClick={() => setMessage("")}>×</button></div>}
        </section>
      </section>
    </div>
  );
}

export function WorkflowStudio(props: Props) { return <ReactFlowProvider><WorkflowStudioInner {...props} /></ReactFlowProvider>; }
