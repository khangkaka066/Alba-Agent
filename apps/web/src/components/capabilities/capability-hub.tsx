"use client";

import { useLocale } from "@/components/locale-provider";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, readError } from "@/lib/api";

type Tab = "skills" | "tools" | "knowledge";
type KnowledgeBase = { id: string; name: string; embedding_model: string };
type SkillPreview = { slug: string; name: string; category: string; description: string; content: string; builtin: boolean; trigger_keywords: string[]; required_tools: string[]; recommended_models: string[] };
type BuiltinTool = { id: string; name: string; description: string; category: string; enabled: boolean };
type Capsule = { capsule_id: string; source_role: string; propagation_scope: string; distilled_heuristic: string };

const TOOL_EXAMPLES: Record<string, Record<string, unknown>> = {
  web_search: { query: "monthly revenue trends" },
  web_scraper: { url: "https://example.com" },
  document_parser: { path: "report.csv" },
  report_exporter: { format: "markdown", filename: "tool-check", content: "# Report\n\nA workspace report." },
  chart_generator: { kind: "bar", labels: ["Jan", "Feb"], values: [4, 7] },
  safe_sql: { database: "configured-source", query: "SELECT 1 AS result", limit: 10 },
  http_webhook: { method: "GET", url: "https://example.com" },
  sandbox_shell: { command: "pwd", timeout: 30 },
  browser_automation: { action: "navigate", arguments: { url: "https://example.com" } },
  media_generation: { kind: "image", prompt: "A clear chart illustration" },
  knowledge_rag: { knowledge_base_id: "knowledge-base-uuid", query: "What does the report say?" },
  peer_workflow: { workflow_id: "workflow-uuid", inputs: {} },
};

export function CapabilityHub({ token, onConnect, tabs = ["skills", "tools", "knowledge"], query = "" }: { token: string; onConnect: () => void; tabs?: Tab[]; query?: string }) {
  const { t } = useLocale();
  const [tab, setTab] = useState<Tab>(tabs[0] ?? "skills");
  useEffect(() => { if (!tabs.includes(tab)) setTab(tabs[0] ?? "skills"); }, [tabs, tab]);
  const [skills, setSkills] = useState<SkillPreview[]>([]);
  const [tools, setTools] = useState<BuiltinTool[]>([]);
  const [capsules, setCapsules] = useState<Capsule[]>([]);
  const needle = query.trim().toLowerCase();
  const visibleSkills = needle ? skills.filter((skill) => `${skill.name} ${skill.category} ${skill.description}`.toLowerCase().includes(needle)) : skills;
  const visibleTools = needle ? tools.filter((tool) => `${tool.name} ${tool.category} ${tool.id} ${tool.description}`.toLowerCase().includes(needle)) : tools;
  const [capsuleId, setCapsuleId] = useState("");
  const [promotionSlug, setPromotionSlug] = useState("");
  const [editingSkill, setEditingSkill] = useState<string | null>(null);
  const [skillDraft, setSkillDraft] = useState<SkillPreview | null>(null);
  const [toolTest, setToolTest] = useState<{ id: string; result: string } | null>(null);
  const [selectedTool, setSelectedTool] = useState<BuiltinTool | null>(null);
  const [toolPayload, setToolPayload] = useState("{}");
  const [newSkillName, setNewSkillName] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [name, setName] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("openai/text-embedding-3-small");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadKnowledgeBases = useCallback(async () => {
    if (!token) return;
    try { setKnowledgeBases(await apiRequest<KnowledgeBase[]>("/api/v1/knowledge-bases", token)); }
    catch (reason) { setError(readError(reason)); }
  }, [token]);

  const loadSkillsAndTools = useCallback(async () => {
    if (!token) return;
    try {
      const [loadedSkills, loadedTools] = await Promise.all([
        apiRequest<SkillPreview[]>("/api/v1/skills", token),
        apiRequest<BuiltinTool[]>("/api/v1/tools/builtin", token),
      ]);
      setSkills(loadedSkills);
      setTools(loadedTools);
      const verifiedCapsules = await apiRequest<Capsule[]>("/api/v1/learning-transfer/capsules", token);
      setCapsules(verifiedCapsules.filter((capsule) => capsule.propagation_scope === "WORKSPACE_VERIFIED"));
    } catch (reason) { setError(readError(reason)); }
  }, [token]);

  useEffect(() => { void loadKnowledgeBases(); void loadSkillsAndTools(); }, [loadKnowledgeBases, loadSkillsAndTools]);

  const importSkills = async (files: FileList | null) => {
    if (!files) return;
    const next = await Promise.all(Array.from(files).filter((file) => file.name.endsWith(".md")).map(async (file) => {
      const content = await file.text();
      try {
        const imported = await apiRequest<SkillPreview>("/api/v1/skills/import", token, { method: "POST", body: JSON.stringify({ content }) });
        return imported;
      } catch (reason) { setError(`${file.name}: ${readError(reason)}`); return null; }
    }));
    const imported = next.filter((item): item is SkillPreview => item !== null);
    setSkills((current) => [...imported, ...current.filter((old) => !imported.some((item) => item.slug === old.slug))]);
    setMessage(imported.length ? `${imported.length} skill file${imported.length === 1 ? "" : "s"} imported to this workspace.` : "Choose one or more valid Markdown skill files.");
  };

  const saveSkill = async () => {
    if (!skillDraft || !token) return;
    setBusy(true); setError("");
    try {
      const front = skillDraft.content.match(/^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$/);
      const parsedBody = front?.[2] ?? skillDraft.content;
      const payload = { slug: skillDraft.slug, name: skillDraft.name, category: skillDraft.category, description: skillDraft.description, trigger_keywords: skillDraft.trigger_keywords, required_tools: skillDraft.required_tools, recommended_models: skillDraft.recommended_models, body: parsedBody };
      const saved = await apiRequest<SkillPreview>(`/api/v1/skills/${encodeURIComponent(skillDraft.slug)}`, token, { method: "PUT", body: JSON.stringify(payload) });
      setSkills((current) => current.map((item) => item.slug === saved.slug ? saved : item)); setEditingSkill(null); setSkillDraft(null); setMessage("Skill instructions saved to this workspace.");
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  const toggleTool = async (tool: BuiltinTool) => {
    if (!token) return;
    try {
      const updated = await apiRequest<{ tool_id: string; enabled: boolean }>(`/api/v1/tools/builtin/${tool.id}/enabled`, token, { method: "PUT", body: JSON.stringify({ enabled: !tool.enabled }) });
      setTools((current) => current.map((item) => item.id === updated.tool_id ? { ...item, enabled: updated.enabled } : item));
    } catch (reason) { setError(readError(reason)); }
  };

  const promoteCapsule = async () => {
    if (!token || !capsuleId || !promotionSlug) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/api/v1/skills/promote-capsule", token, { method: "POST", body: JSON.stringify({ capsule_id: capsuleId, slug: promotionSlug }) });
      await loadSkillsAndTools(); setMessage("Verified capsule added to the skill's learned best practices.");
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  const runToolTest = async () => {
    if (!token || !selectedTool) return;
    let payload: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(toolPayload);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Payload must be a JSON object.");
      payload = parsed as Record<string, unknown>;
    } catch (reason) { setToolTest({ id: selectedTool.id, result: `Invalid JSON: ${readError(reason)}` }); return; }
    setBusy(true); setError(""); setToolTest({ id: selectedTool.id, result: "Running…" });
    try {
      const result = await apiRequest<{ result: unknown }>(`/api/v1/tools/builtin/${selectedTool.id}/test`, token, { method: "POST", body: JSON.stringify({ payload }) });
      setToolTest({ id: selectedTool.id, result: JSON.stringify(result.result, null, 2) });
    } catch (reason) { setToolTest({ id: selectedTool.id, result: readError(reason) }); }
    finally { setBusy(false); }
  };

  const createKnowledgeBase = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if (!name.trim() || !token) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest<KnowledgeBase>("/api/v1/knowledge-bases", token, { method: "POST", body: JSON.stringify({ name: name.trim(), embedding_model: embeddingModel }) });
      setName(""); await loadKnowledgeBases(); setMessage("Knowledge base created in this workspace.");
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  const uploadDocument = async (knowledgeBaseId: string, file?: File) => {
    if (!file || !token) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents?filename=${encodeURIComponent(file.name)}`, token, { method: "POST", headers: { "content-type": "application/octet-stream" }, body: file });
      setMessage(`${file.name} indexed into the selected knowledge base.`);
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };

  return <section className="capability-hub">
    <div className="capability-tabs" hidden={tabs.length < 2} role="tablist" aria-label="Workspace capabilities">
      {tabs.includes("skills") && <button role="tab" aria-selected={tab === "skills"} className={tab === "skills" ? "is-active" : ""} onClick={() => setTab("skills")}>{t("hub.skills")} <span>{skills.length}</span></button>}
      {tabs.includes("tools") && <button role="tab" aria-selected={tab === "tools"} className={tab === "tools" ? "is-active" : ""} onClick={() => setTab("tools")}>{t("hub.tools")}</button>}
      {tabs.includes("knowledge") && <button role="tab" aria-selected={tab === "knowledge"} className={tab === "knowledge" ? "is-active" : ""} onClick={() => setTab("knowledge")}>{t("hub.knowledge")} <span>{knowledgeBases.length}</span></button>}
    </div>
    {message && <p className="capability-message" role="status">{message}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}

    {tab === "skills" && <div className="capability-view">
      <div className="capability-section-head"><div><h2>Agent skill files</h2><p>Reusable skill instructions for your agents.</p></div><button className="button button-primary" onClick={() => token ? inputRef.current?.click() : onConnect()}>{token ? "Add SKILL.md" : "Connect to add a skill"}</button><input ref={inputRef} className="sr-only" type="file" accept=".md,text/markdown" multiple onChange={(event) => { void importSkills(event.target.files); event.target.value = ""; }} /></div>
      {token && <div className="skill-create-bar"><input aria-label="New skill name" value={newSkillName} placeholder="Create a custom skill name" onChange={(event) => setNewSkillName(event.target.value)} /><button className="button button-primary" disabled={!newSkillName.trim()} onClick={async () => { if (!token) return; const title = newSkillName.trim(); const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); if (!slug) { setError("Use a name containing letters or numbers."); return; } try { const saved = await apiRequest<SkillPreview>("/api/v1/skills", token, { method: "POST", body: JSON.stringify({ slug, name: title, category: "custom", description: "Workspace-authored agent skill", body: "## Standard operating procedure\n\nDescribe the steps, checks, and guardrails for this skill." }) }); setSkills((current) => [saved, ...current]); setNewSkillName(""); setMessage("Custom skill created."); } catch (reason) { setError(readError(reason)); } }}>Create skill</button></div>}
      {token && <div className="capsule-promotion"><div><strong>Promote verified learning</strong><p>Only active workspace-verified capsules with sufficient positive transfer evidence can be added.</p></div><select aria-label="Verified capsule" value={capsuleId} onChange={(event) => setCapsuleId(event.target.value)}><option value="">Choose a capsule</option>{capsules.map((capsule) => <option key={capsule.capsule_id} value={capsule.capsule_id}>{capsule.source_role} · {capsule.capsule_id.slice(0, 8)}</option>)}</select><select aria-label="Target skill" value={promotionSlug} onChange={(event) => setPromotionSlug(event.target.value)}><option value="">Choose a skill</option>{skills.map((skill) => <option key={skill.slug} value={skill.slug}>{skill.name}</option>)}</select><button className="button button-quiet" disabled={busy || !capsuleId || !promotionSlug} onClick={() => void promoteCapsule()}>{busy ? "Promoting…" : "Promote to skill"}</button></div>}
      {visibleSkills.length ? <div className="skill-list">{visibleSkills.map((skill) => <details className="skill-row" key={skill.slug}><summary><span className="skill-file-mark">MD</span><span className="skill-row__copy"><strong>{skill.name}</strong><small>{skill.category} · {skill.description}</small></span><span className="skill-open">{skill.builtin ? "Built in" : "Workspace"}</span></summary>{editingSkill === skill.slug && skillDraft ? <div className="skill-editor"><label>Name<input value={skillDraft.name} onChange={(event) => setSkillDraft({ ...skillDraft, name: event.target.value })} /></label><label>Description<input value={skillDraft.description} onChange={(event) => setSkillDraft({ ...skillDraft, description: event.target.value })} /></label><label>SKILL.md<textarea value={skillDraft.content} onChange={(event) => setSkillDraft({ ...skillDraft, content: event.target.value })} rows={16} /></label><button className="button button-primary" disabled={busy} onClick={() => void saveSkill()}>Save workspace version</button><button className="button button-quiet" onClick={() => { setEditingSkill(null); setSkillDraft(null); }}>Cancel</button></div> : <><pre>{skill.content}</pre><div className="skill-row-actions"><button className="text-button" onClick={() => { setEditingSkill(skill.slug); setSkillDraft({ ...skill, content: skill.content }); }}>Edit instructions</button><a className="text-button" href={`/api/v1/skills/${skill.slug}/export`} onClick={async (event) => { event.preventDefault(); try { const response = await fetch(`/api/v1/skills/${skill.slug}/export`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error("Skill export failed"); const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${skill.slug}.md`; anchor.click(); URL.revokeObjectURL(url); } catch (reason) { setError(readError(reason)); } }}>Export .md</a></div></>}</details>)}</div> : <div className="capability-empty capability-empty--compact"><span className="capability-empty-mark">MD</span><h3>No workspace skills yet</h3><p>Import a SKILL.md file or create a custom skill to get started.</p></div>}
    </div>}

    {tab === "tools" && <div className="capability-view">
      <div className="capability-section-head"><div><h2>Workspace tools</h2><p>Connected model, retrieval, and computer services used by workflows.</p></div><a className="button button-quiet" href="/settings/providers">Manage providers</a></div>
      <div className="tool-capability-list">
        {visibleTools.map((tool) => <article key={tool.id}><span className={tool.enabled ? "tool-state-dot" : "tool-state-dot is-disabled"} /><div><strong>{tool.name}</strong><p>{tool.description}</p><small>{tool.category} · {tool.id}</small></div><button className="text-button" disabled={busy || !tool.enabled} onClick={() => { setSelectedTool(tool); setToolPayload(JSON.stringify(TOOL_EXAMPLES[tool.id] ?? {}, null, 2)); setToolTest(null); }}>Test</button><button className="button button-quiet" aria-pressed={tool.enabled} onClick={() => void toggleTool(tool)}>{tool.enabled ? "Enabled" : "Disabled"}</button></article>)}
        <article><span className="tool-state-dot" /><div><strong>Model gateway</strong><p>Provider credentials and default models are managed in System settings.</p></div><a href="/settings/providers">Configure</a></article>
        <article><span className="tool-state-dot" /><div><strong>Knowledge retrieval</strong><p>Workspace-scoped Qdrant search is available to configured workflow nodes.</p></div><button className="text-button" onClick={() => setTab("knowledge")}>Open knowledge bases</button></article>
        <article><span className="tool-state-dot" /><div><strong>Computer sandbox</strong><p>Docker and configured cloud providers run isolated coding and browser tasks.</p></div><a href="/settings/providers">Review providers</a></article>
      </div>
      {selectedTool && <section className="tool-playground" aria-label={`${selectedTool.name} playground`}><div className="capability-section-head"><div><h3>Test {selectedTool.name}</h3><p>Enter the inputs for this workspace. Some tools need a configured provider, computer, or data source.</p></div><button className="text-button" onClick={() => { setSelectedTool(null); setToolTest(null); }}>Close</button></div><label className="field"><span>JSON payload</span><textarea value={toolPayload} onChange={(event) => setToolPayload(event.target.value)} rows={7} spellCheck={false} /></label><button className="button button-primary" disabled={busy} onClick={() => void runToolTest()}>{busy ? "Running…" : "Run tool"}</button>{toolTest?.id === selectedTool.id && <pre className="tool-test-result" role="status">{toolTest.result}</pre>}</section>}
      <div className="capability-note"><strong>MCP inventory</strong><p>The workspace tool list is supplied by connected adapters. This control plane does not currently expose a server inventory endpoint, so no unverified MCP servers are shown here.</p></div>
    </div>}

    {tab === "knowledge" && <div className="capability-view">
      <div className="capability-section-head"><div><h2>Workspace knowledge</h2><p>Documents are indexed into tenant-scoped knowledge bases.</p></div><span className="connection-pill"><span className={token ? "status-dot" : ""} />{token ? "Workspace connected" : "Connect a workspace to manage data"}</span></div>
      {token && <form className="knowledge-create" onSubmit={(event) => void createKnowledgeBase(event)}><label className="field"><span>Knowledge base name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Quarterly research" required /></label><label className="field"><span>Embedding model</span><input value={embeddingModel} onChange={(event) => setEmbeddingModel(event.target.value)} required /></label><button className="button button-primary" disabled={busy || !name.trim()}>{busy ? "Creating…" : "Create knowledge base"}</button></form>}
      {knowledgeBases.length ? <div className="knowledge-list">{knowledgeBases.map((base) => <article className="knowledge-row" key={base.id}><div className="knowledge-row__icon" aria-hidden="true">Q</div><div className="knowledge-row__copy"><strong>{base.name}</strong><small>{base.embedding_model} · tenant-isolated</small></div><label className="button button-quiet knowledge-upload">Add document<input type="file" accept=".pdf,.docx,.md,.markdown,.csv,.txt" disabled={!token || busy} onChange={(event) => { void uploadDocument(base.id, event.target.files?.[0]); event.target.value = ""; }} /></label></article>)}</div> : <div className="capability-empty capability-empty--compact"><h3>{token ? "No knowledge bases yet" : "Connect a workspace first"}</h3><p>{token ? "Create a knowledge base above, then index PDF, DOCX, Markdown, or CSV documents." : "Sign in to list and manage tenant knowledge."}</p></div>}
    </div>}
  </section>;
}
