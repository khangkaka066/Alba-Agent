"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { useShell } from "@/components/shell/shell-context";
import { apiRequest } from "@/lib/api";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { FileGlyph } from "./file-glyph";
import { useWorkspace, type Attachment, type ContextRef } from "./workspace-context";

type Found = Attachment & { run_status: string };

/** Files of earlier tasks, searched by file or task name. Opened with the pill or by typing `@` in the prompt. */
function ArtifactPicker({ onClose, initialCategory = "Artifacts" }: { onClose: () => void; initialCategory?: ContextRef["kind"] }) {
  const { t } = useLocale();
  const shell = useShell();
  const { token, attachments, addAttachment, folder, addContext, contextRefs } = useWorkspace();
  const categories: ContextRef["kind"][] = ["Files", "Folders", "Artifacts", "PastRuns", "Skills", "Web", "Knowledge"];
  const [category, setCategory] = useState<ContextRef["kind"]>(initialCategory);
  const [error, setError] = useState("");
  const [refs, setRefs] = useState<ContextRef[]>([]);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Found[] | null>(null);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    if (!token || category !== "Artifacts") return;
    let stopped = false;
    const timer = window.setTimeout(() => {
      void apiRequest<Array<Found & { run_name: string }>>(`/api/v1/artifacts/search?q=${encodeURIComponent(query)}&limit=30`, token)
        .then((rows) => { if (!stopped) { setItems(rows); setActive(0); } }).catch(() => { if (!stopped) setItems([]); });
    }, 200);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [query, token, category]);
  useEffect(() => {
    setActive(0); setError(""); setRefs([]);
    const contains = (label: string) => label.toLowerCase().includes(query.toLowerCase());
    if (category === "Files" || category === "Folders") {
      const paths = category === "Files" ? folder?.files.map((file) => file.path) ?? [] : [...new Set(folder?.files.flatMap((file) => file.path.includes("/") ? [file.path.slice(0, file.path.lastIndexOf("/"))] : []) ?? [])];
      setRefs(paths.filter(contains).map((path) => ({ kind: category, id: path, label: path })));
      return;
    }
    if (category === "Web") {
      try { const url = new URL(query); if (["https:", "http:"].includes(url.protocol)) setRefs([{ kind: "Web", id: url.href, label: url.href }]); } catch { /* Wait for a valid web address. */ }
      return;
    }
    if (category === "PastRuns") {
      setRefs(shell.conversations.filter((item) => contains(item.name)).map((item) => ({ kind: category, id: item.run.id, label: item.name })));
      return;
    }
    if (category === "Artifacts" || !token) return;
    let stopped = false;
    const path = category === "Skills" ? "/api/v1/skills" : "/api/v1/knowledge-bases";
    void apiRequest<Array<Record<string, unknown>>>(path, token).then((rows) => {
      if (!stopped) setRefs(rows.map((row) => ({ kind: category, id: String(row.slug ?? row.id), label: String(row.name ?? row.title ?? row.slug ?? row.id) })).filter((row) => contains(row.label)));
    }).catch(() => { if (!stopped) setError(t("studio.contextFailed")); });
    return () => { stopped = true; };
  }, [category, folder, query, token, t, shell.conversations]);
  const available = category === "Artifacts" ? (items ?? []).filter((item) => !attachments.some((entry) => entry.run_id === item.run_id && entry.filename === item.filename)) : [];
  const references = refs.filter((item) => !contextRefs.some((entry) => entry.id === item.id));
  const count = category === "Artifacts" ? available.length : references.length;
  const chooseActive = () => { if (category === "Artifacts" && available[active]) pick(available[active]); else if (references[active]) { addContext(references[active]); onClose(); } };
  const pick = (item: Found) => { addAttachment({ run_id: item.run_id, filename: item.filename, run_name: item.run_name, size_bytes: item.size_bytes, mime_type: item.mime_type }); onClose(); };
  const keys = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => count ? (value + 1) % count : 0); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => count ? (value - 1 + count) % count : 0); }
    else if (event.key === "Enter") { event.preventDefault(); chooseActive(); }
  };
  return <div className="artifact-picker" role="dialog" aria-label={t("attach.title")} onKeyDown={keys}>
    <div className="ag-context-categories" role="group" aria-label={t("studio.contextCategories")}>{categories.map((kind) => <button type="button" key={kind} aria-pressed={category === kind} onClick={() => { setCategory(kind); setQuery(""); input.current?.focus(); }}>{t(`interface.context.${kind}`)}</button>)}</div>
    <input ref={input} role="combobox" aria-expanded="true" aria-controls="nexus-context-options" aria-activedescendant={count ? `nexus-context-${active}` : undefined} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("attach.search")} aria-label={t("attach.search")} spellCheck={false} />
    <div id="nexus-context-options" role="listbox" aria-label={t("attach.title")}>
      {category === "Artifacts" && items === null && <p className="artifact-picker__note">{t("common.loading")}</p>}
      {category === "Artifacts" && items?.length === 0 && <p className="artifact-picker__note">{t(query ? "attach.noMatch" : "attach.empty")}</p>}
      {available.map((item, index) => <button type="button" role="option" aria-selected={index === active} id={`nexus-context-${index}`} key={`${item.run_id}/${item.filename}`}
        className={`artifact-picker__item ${index === active ? "is-active" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => pick(item)}>
        <FileGlyph kind={classifyArtifact(item.filename, item.mime_type).kind} /><span className="artifact-picker__name">{item.filename}</span>
        <span className="artifact-picker__task">{item.run_name}</span></button>)}
      {references.map((item, index) => <button type="button" role="option" id={`nexus-context-${index}`} aria-selected={index === active} key={item.id} className={`artifact-picker__item ${index === active ? "is-active" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => { addContext(item); onClose(); }}><span className="artifact-picker__name">{item.label}</span><small>@{item.kind}</small></button>)}
      {category !== "Artifacts" && !references.length && <p className="artifact-picker__note">{t(category === "Web" ? "studio.webContextHint" : "attach.noMatch")}</p>}
      {error && <p className="ag-problem" role="alert">{error}</p>}
    </div>
  </div>;
}

/** The files the next team starts from, shown as removable chips, plus the way to add more. */
export function AttachmentBar({ open, onOpenChange, initialCategory }: { open: boolean; onOpenChange: (open: boolean) => void; initialCategory?: ContextRef["kind"] }) {
  const { t } = useLocale();
  const { attachments, removeAttachment, contextRefs, removeContext, uploads, removeUpload, busy } = useWorkspace();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) onOpenChange(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open, onOpenChange]);
  return <div className="attachment-bar" ref={root}>
    {uploads.map((item) => <span className={`chip chip--attached nx-upload-chip is-${item.status}`} key={item.id} aria-busy={item.status === "uploading"} title={item.error ?? item.filename}>
      <FileGlyph kind={classifyArtifact(item.filename, item.mime_type).kind} /><span className="nx-upload-name">{item.filename}</span><small>{item.status === "uploading" ? t("upload.uploading") : item.status === "error" ? t("upload.failed") : item.size_bytes < 1000 ? `${item.size_bytes} B` : item.size_bytes < 1_000_000 ? `${(item.size_bytes / 1000).toFixed(1)} KB` : `${(item.size_bytes / 1_000_000).toFixed(1)} MB`}</small>
      <button type="button" disabled={busy} aria-label={t("attach.remove", { name: item.filename })} onClick={() => removeUpload(item.id)}>×</button>
      {item.error && <span className="nx-upload-file-error" role="alert">{item.error}</span>}
    </span>)}
    {contextRefs.map((item) => <span className="ag-chip ag-context-chip" key={item.id} title={item.id}>@{item.label}<button type="button" aria-label={t("attach.remove", { name: item.label })} onClick={() => removeContext(item.id)}>×</button></span>)}
    {attachments.map((item) => <span className="chip chip--attached" key={`${item.run_id}/${item.filename}`} title={item.run_name ? t("attach.fromTask", { task: item.run_name }) : item.filename}>
      <FileGlyph kind={classifyArtifact(item.filename, item.mime_type).kind} />{item.filename.split("/").pop()}
      <button type="button" aria-label={t("attach.remove", { name: item.filename })} onClick={() => removeAttachment(item)}>×</button></span>)}
    {open && <ArtifactPicker initialCategory={initialCategory} onClose={() => { onOpenChange(false); window.setTimeout(() => window.dispatchEvent(new Event("nexus:focus-composer")), 0); }} />}
  </div>;
}

/** True when `@` is typed at the start of a word, which is when it means "attach a file". */
export function atWordStart(field: HTMLTextAreaElement): boolean {
  const position = field.selectionStart;
  return position === 0 || /\s/.test(field.value[position - 1] ?? "");
}
