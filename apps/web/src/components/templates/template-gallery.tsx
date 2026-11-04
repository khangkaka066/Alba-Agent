"use client";

import { useEffect, useMemo, useState } from "react";
import { Background, BackgroundVariant, ReactFlow, ReactFlowProvider, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { apiRequest, readError, type JsonRecord } from "@/lib/api";
import { kindMeta, nodeTypes, type CanvasKind, type StudioNodeData } from "@/components/canvas/node-types";

type TemplateEntry = {
  id: string;
  title: string;
  summary: string;
  description: string;
  category: string;
  tags: string[];
  required_connections: string[];
  readiness_notes: string[];
  workflow: { nodes?: JsonRecord[]; edges?: JsonRecord[] };
  layout: Record<string, { x: number; y: number }>;
  has_bot: boolean;
  has_routine: boolean;
};
type InstantiatedTemplate = { workflow_id: string | null; bot_id: string | null; routine_ids: string[] };

function previewGraph(template: TemplateEntry): { nodes: Node<StudioNodeData>[]; edges: Edge[] } {
  const nodes = (template.workflow.nodes ?? []).map((raw, index): Node<StudioNodeData> => {
    const kind = (raw.kind === "sandbox" ? "nexusgen" : raw.kind) as CanvasKind;
    const position = template.layout[String(raw.id)] ?? { x: index * 260, y: 150 };
    return {
      id: String(raw.id), type: kind, position,
      data: {
        label: String(raw.label ?? kindMeta[kind]?.label ?? "Workflow step"),
        description: kindMeta[kind]?.description ?? "Template workflow step",
        config: {},
      },
    };
  });
  const edges = (template.workflow.edges ?? []).map((raw, index): Edge => ({
    id: `preview-${index}-${String(raw.source)}-${String(raw.target)}`,
    source: String(raw.source), target: String(raw.target),
    label: typeof raw.route === "string" ? raw.route : undefined,
    style: { stroke: "#9eafa1", strokeWidth: 1.6 },
  }));
  return { nodes, edges };
}

function TemplatePreview({ template }: { template: TemplateEntry }) {
  const graph = useMemo(() => previewGraph(template), [template]);
  return <div className="template-preview" aria-label={`${template.title} workflow graph`}>
    <ReactFlowProvider>
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.16 }}
        minZoom={0.18}
        maxZoom={0.8}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#dfe7df" />
      </ReactFlow>
    </ReactFlowProvider>
  </div>;
}

export function TemplateGallery({ token, onCreated }: { token: string; onCreated: (workflowId: string, result: InstantiatedTemplate) => void }) {
  const [templates, setTemplates] = useState<TemplateEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void apiRequest<TemplateEntry[]>("/api/v1/templates", "")
      .then((entries) => { if (active) setTemplates(entries); })
      .catch((reason: unknown) => { if (active) setError(readError(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const instantiate = async (template: TemplateEntry) => {
    if (!token) { setError("Connect a workspace before adding a template."); return; }
    setBusyId(template.id); setError(""); setMessage("");
    try {
      const result = await apiRequest<InstantiatedTemplate & { template_id: string }>(
        `/api/v1/templates/${template.id}/instantiate`, token,
        { method: "POST", body: JSON.stringify({}) },
      );
      setMessage(`${template.title} added to your workspace${result.bot_id ? ", including its teammate and routine" : ""}.`);
      if (result.workflow_id) onCreated(result.workflow_id, result);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusyId(null); }
  };

  return <section className="template-gallery" aria-label="Workflow template gallery">
    <div className="template-gallery__intro"><div><span className="eyebrow">START WITH A PLAYBOOK</span><h2>Template gallery</h2><p>Preview a complete workflow, then add it to this workspace. Templates create scoped workflow, knowledge, teammate, and routine records where applicable.</p></div><span className="template-count">{templates.length} templates</span></div>
    {message && <div className="template-notice" role="status">{message}</div>}
    {error && <div className="template-error" role="alert">{error}</div>}
    {loading ? <div className="template-loading">Loading workspace templates…</div> : <div className="template-grid">{templates.map((template, index) => (
      <article className="template-card" key={template.id}>
        <div className="template-card__heading"><span className={`template-number template-number--${index + 1}`}>0{index + 1}</span><span className="template-category">{template.category}</span></div>
        <h3>{template.title}</h3><p className="template-summary">{template.summary}</p>
        <TemplatePreview template={template} />
        <p className="template-description">{template.description}</p>
        <div className="template-tags">{template.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
        {(template.has_bot || template.has_routine) && <div className="template-includes">{template.has_bot && <span>✳ Persistent teammate</span>}{template.has_routine && <span>◷ Scheduled routine</span>}</div>}
        {(template.required_connections.length > 0 || template.readiness_notes.length > 0) && <details className="template-requirements"><summary>Setup notes</summary><ul>{[...template.required_connections, ...template.readiness_notes].map((note) => <li key={note}>{note}</li>)}</ul></details>}
        <button className="button button-primary template-add" disabled={!token || busyId !== null} onClick={() => void instantiate(template)}>{busyId === template.id ? "Adding to workspace…" : "Use this template →"}</button>
      </article>
    ))}</div>}
  </section>;
}
