"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { apiRequest } from "@/lib/api";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { FileGlyph } from "./file-glyph";
import { useWorkspace, type Attachment } from "./workspace-context";

type Found = Attachment & { run_status: string };

/** Files of earlier tasks, searched by file or task name. Opened with the pill or by typing `@` in the prompt. */
function ArtifactPicker({ onClose }: { onClose: () => void }) {
  const { t } = useLocale();
  const { token, attachments, addAttachment } = useWorkspace();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Found[] | null>(null);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => {
    if (!token) return;
    let stopped = false;
    const timer = window.setTimeout(() => {
      void apiRequest<Array<Found & { run_name: string }>>(`/api/v1/artifacts/search?q=${encodeURIComponent(query)}&limit=30`, token)
        .then((rows) => { if (!stopped) { setItems(rows); setActive(0); } }).catch(() => { if (!stopped) setItems([]); });
    }, 200);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [query, token]);
  const taken = (item: Attachment) => attachments.some((entry) => entry.run_id === item.run_id && entry.filename === item.filename);
  const pick = (item: Found) => { addAttachment({ run_id: item.run_id, filename: item.filename, run_name: item.run_name, size_bytes: item.size_bytes, mime_type: item.mime_type }); onClose(); };
  const keys = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
    else if (event.key === "ArrowDown" && items?.length) { event.preventDefault(); setActive((value) => Math.min(value + 1, items.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(value - 1, 0)); }
    else if (event.key === "Enter" && items?.[active]) { event.preventDefault(); pick(items[active]); }
  };
  return <div className="artifact-picker" role="dialog" aria-label={t("attach.title")} onKeyDown={keys}>
    <input ref={input} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("attach.search")} aria-label={t("attach.search")} spellCheck={false} />
    <div role="listbox" aria-label={t("attach.title")}>
      {items === null && <p className="artifact-picker__note">{t("common.loading")}</p>}
      {items?.length === 0 && <p className="artifact-picker__note">{t(query ? "attach.noMatch" : "attach.empty")}</p>}
      {items?.map((item, index) => <button type="button" role="option" aria-selected={index === active} key={`${item.run_id}/${item.filename}`} disabled={taken(item)}
        className={`artifact-picker__item ${index === active ? "is-active" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => pick(item)}>
        <FileGlyph kind={classifyArtifact(item.filename, item.mime_type).kind} /><span className="artifact-picker__name">{item.filename}</span>
        <span className="artifact-picker__task">{item.run_name}</span></button>)}
    </div>
  </div>;
}

/** The files the next team starts from, shown as removable chips, plus the way to add more. */
export function AttachmentBar({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useLocale();
  const { attachments, removeAttachment } = useWorkspace();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) onOpenChange(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open, onOpenChange]);
  return <div className="attachment-bar" ref={root}>
    {attachments.map((item) => <span className="chip chip--attached" key={`${item.run_id}/${item.filename}`} title={item.run_name ? t("attach.fromTask", { task: item.run_name }) : item.filename}>
      <FileGlyph kind={classifyArtifact(item.filename, item.mime_type).kind} />{item.filename.split("/").pop()}
      <button type="button" aria-label={t("attach.remove", { name: item.filename })} onClick={() => removeAttachment(item)}>×</button></span>)}
    <button type="button" className="attach-pill" aria-expanded={open} onClick={() => onOpenChange(!open)} title={t("attach.title")}>＠ {t("attach.pill")}</button>
    {open && <ArtifactPicker onClose={() => onOpenChange(false)} />}
  </div>;
}

/** True when `@` is typed at the start of a word, which is when it means "attach a file". */
export function atWordStart(field: HTMLTextAreaElement): boolean {
  const position = field.selectionStart;
  return position === 0 || /\s/.test(field.value[position - 1] ?? "");
}
