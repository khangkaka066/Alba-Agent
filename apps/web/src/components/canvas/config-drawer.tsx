"use client";

import { useEffect, useState } from "react";
import { configFields, kindMeta, type CanvasKind, type StudioNodeData } from "./node-types";
import { apiRequest } from "@/lib/api";

type Props = { kind: CanvasKind; data: StudioNodeData; onChange: (data: StudioNodeData) => void; onClose: () => void };
type SkillOption = { slug: string; name: string; description: string };
type ToolOption = { id: string; name: string; description: string; enabled: boolean };

export function ConfigDrawer({ kind, data, onChange, onClose }: Props) {
  const fields = configFields[kind];
  const primaryKeys = kind === "autogen"
    ? new Set(["coder_instructions", "sandbox_provider", "timeout_seconds", "max_turns"])
    : kind === "crew"
      ? new Set(["agents", "tasks", "model", "output_schema"])
      : new Set(fields.map((field) => field.key));
  const primaryFields = fields.filter((field) => primaryKeys.has(field.key));
  const advancedFields = fields.filter((field) => !primaryKeys.has(field.key));
  const [skills, setSkills] = useState<SkillOption[]>([]);
  const [tools, setTools] = useState<ToolOption[]>([]);
  useEffect(() => {
    if (!data.token || (kind !== "crew" && kind !== "autogen")) return;
    let alive = true;
    void Promise.all([apiRequest<SkillOption[]>("/api/v1/skills", data.token), apiRequest<ToolOption[]>("/api/v1/tools/builtin", data.token)])
      .then(([skillRows, toolRows]) => { if (alive) { setSkills(skillRows); setTools(toolRows.filter((tool) => tool.enabled)); } }).catch(() => undefined);
    return () => { alive = false; };
  }, [data.token, kind]);
  const listValue = (key: string) => (data.config[key] ?? "").split(/[\n,]/).map((value) => value.trim()).filter(Boolean);
  const setList = (key: string, values: string[]) => onChange({ ...data, config: { ...data.config, [key]: values.join("\n") } });
  const renderField = (field: (typeof fields)[number]) => <label className="field" key={field.key}><span>{field.label}</span>{field.choices ? <select value={data.config[field.key] ?? field.choices[0]} onChange={(event) => onChange({ ...data, config: { ...data.config, [field.key]: event.target.value } })}>{field.choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}</select> : field.multiline ? <textarea rows={field.key === "output_schema" || field.key === "input_schema" ? 4 : 3} value={data.config[field.key] ?? ""} placeholder={field.placeholder} onChange={(event) => onChange({ ...data, config: { ...data.config, [field.key]: event.target.value } })} /> : <input value={data.config[field.key] ?? ""} placeholder={field.placeholder} onChange={(event) => onChange({ ...data, config: { ...data.config, [field.key]: event.target.value } })} />}</label>;
  const capabilities = (kind === "crew" || kind === "autogen") && <section className="skill-tool-picker"><span className="eyebrow">Agent capabilities</span><label className="field"><span>Attach skills</span><select multiple value={listValue("skill_ids")} onChange={(event) => setList("skill_ids", Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>{skills.map((skill) => <option key={skill.slug} value={skill.slug}>{skill.name} — {skill.description}</option>)}</select></label><label className="field"><span>Attach built-in tools</span><select multiple value={listValue("tool_ids")} onChange={(event) => setList("tool_ids", Array.from(event.currentTarget.selectedOptions, (option) => option.value))}>{tools.map((tool) => <option key={tool.id} value={tool.id}>{tool.name}</option>)}</select></label><small>Use Cmd/Ctrl-click to select several. Full skill instructions load only for these assignments.</small></section>;
  return (
    <aside className="config-drawer">
      <div className="drawer-head"><div><span className="eyebrow">Node settings</span><h2>{kindMeta[kind].label}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close node settings">×</button></div>
      <label className="field"><span>Node name</span><input value={data.label} onChange={(event) => onChange({ ...data, label: event.target.value })} /></label>
      <label className="field"><span>Description</span><textarea rows={2} value={data.description} onChange={(event) => onChange({ ...data, description: event.target.value })} /></label>
      {primaryFields.map(renderField)}
      {(advancedFields.length > 0 || capabilities) && <details className="drawer-advanced"><summary>Advanced settings</summary>{advancedFields.map(renderField)}{capabilities}</details>}
      <div className="drawer-note"><span>◇</span><p>Configuration is saved as part of this workflow definition and included in JSON/YAML exports.</p></div>
    </aside>
  );
}
