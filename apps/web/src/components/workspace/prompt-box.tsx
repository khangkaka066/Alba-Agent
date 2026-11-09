"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { ModelPicker } from "@/components/model-picker";
import { EffortPicker } from "@/components/effort-picker";
import { Icon } from "@/components/shell/icons";
import { getDesktop } from "@/lib/desktop";
import { useWorkspace, type ExecutionMode, type ContextRef } from "./workspace-context";
import { ProjectSelector } from "./project-selector";
import { PermissionSelector } from "./permission-selector";
import { usePreferences } from "@/components/settings/preferences-provider";
import { AttachmentBar, atWordStart } from "./attachments";
import { isFinished } from "@/lib/workspace.mjs";

/** The Web Speech API where it exists. The desktop app (Electron) ships without the speech service, so it gets no microphone button. */
type Recognition = { lang: string; interimResults: boolean; continuous: boolean; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null; onend: (() => void) | null; onerror: ((event: { error: string }) => void) | null; start: () => void; stop: () => void };
type RecognitionConstructor = new () => Recognition;
function recognitionClass(): RecognitionConstructor | null {
  if (typeof window === "undefined" || getDesktop()) return null;
  const scope = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onOpenSettings: () => void;
  placeholder: string;
  busy: boolean;
  canSend: boolean;
  rows?: number;
  autoFocus?: boolean;
  label: string;
  /** Called when "/" is typed at the start of a word: the owner decides what to open. */
  onSlash?: () => void;
};

/** The message box of Antigravity: one rounded box with attach, model, permissions, dictation and send. Shared by the home screen and the conversation. */
export function PromptBox({ value, onChange, onSubmit, onOpenSettings, placeholder, busy, canSend, rows = 1, autoFocus, label, onSlash }: Props) {
  const { t, locale } = useLocale();
  const workspace = useWorkspace();
  const { preferences } = usePreferences();
  const modes: ExecutionMode[] = ["auto", "agent", "plan", "ask"];
  const working = busy || (workspace.runId !== null && !isFinished(workspace.run.status));
  const stopping = working && !value.trim();
  const [picking, setPicking] = useState(false);
  const [pickCategory, setPickCategory] = useState<ContextRef["kind"]>("Artifacts");
  const [listening, setListening] = useState(false);
  const [dictationNote, setDictationNote] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);
  const files = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const blocked = workspace.uploading || workspace.uploads.some((item) => item.status === "error");
  const recognition = useRef<Recognition | null>(null);
  const [canDictate, setCanDictate] = useState(false);
  useEffect(() => setCanDictate(recognitionClass() !== null), []);
  useEffect(() => {
    const focus = () => field.current?.focus();
    window.addEventListener("nexus:focus-composer", focus);
    return () => window.removeEventListener("nexus:focus-composer", focus);
  }, []);
  useEffect(() => {
    const send = () => { if (field.current && document.contains(field.current)) onSubmit(); };
    window.addEventListener("nexus:run", send);
    return () => window.removeEventListener("nexus:run", send);
  }, [onSubmit]);
  useEffect(() => () => recognition.current?.stop(), []);

  const dictate = () => {
    if (listening) { recognition.current?.stop(); return; }
    const Recognizer = recognitionClass();
    if (!Recognizer) return;
    const base = value ? `${value.trimEnd()} ` : "";
    const engine = new Recognizer();
    engine.lang = locale === "vi" ? "vi-VN" : "en-US";
    engine.interimResults = true; engine.continuous = false;
    engine.onresult = (event) => { onChange(base + Array.from(event.results).map((result) => result[0]?.transcript ?? "").join("")); };
    engine.onerror = (event) => { setDictationNote(t(event.error === "not-allowed" ? "prompt.micDenied" : "prompt.micFailed")); };
    engine.onend = () => setListening(false);
    recognition.current = engine; setDictationNote(""); setListening(true);
    try { engine.start(); } catch { setListening(false); }
  };

  return <div className="nx-chat-composer"><ProjectSelector /><div className={`ag-prompt ${dragging ? "is-file-drop" : ""}`} onDragOver={(event) => {
    if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); event.dataTransfer.dropEffect = busy ? "none" : "copy"; setDragging(!busy); }
  }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDrop={(event) => {
    if (!event.dataTransfer.files.length) return;
    event.preventDefault(); setDragging(false); if (!busy) workspace.uploadFiles(Array.from(event.dataTransfer.files));
  }} onPaste={(event) => { if (event.clipboardData.files.length) { event.preventDefault(); if (!busy) workspace.uploadFiles(Array.from(event.clipboardData.files)); } }}>
    <input ref={files} className="nx-upload-input" type="file" multiple hidden aria-label={t("upload.choose")} onChange={(event) => { workspace.uploadFiles(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ""; }} />
    <textarea ref={field} aria-label={label} rows={rows} autoFocus={autoFocus} value={value} placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing) return;
        if (event.key === "Tab" && event.shiftKey) { event.preventDefault(); workspace.setExecutionMode(modes[(modes.indexOf(workspace.executionMode) + 1) % modes.length]); return; }
        if (event.key === "@" && atWordStart(event.currentTarget)) { event.preventDefault(); setPickCategory("Files"); setPicking(true); return; }
        if (event.key === "Escape" && working && !picking) { event.preventDefault(); event.stopPropagation(); void workspace.stop(); return; }
        if (event.key === "/" && onSlash && atWordStart(event.currentTarget) && value.trim() === "") { event.preventDefault(); onSlash(); return; }
        if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!blocked) onSubmit(); }
      }} />
    <AttachmentBar open={picking} onOpenChange={setPicking} initialCategory={pickCategory} />
    <div className="ag-prompt__bar">
      <button type="button" className="ag-iconbtn nx-upload-trigger" aria-label={t("upload.choose")} title={t("upload.choose")} disabled={busy || !workspace.token} onClick={() => files.current?.click()}><Icon name="plus" size={18} /></button>
      <ModelPicker compact disabled={busy} onOpenSettings={onOpenSettings} />
      <EffortPicker disabled={busy} />
      <span className="ag-spacer" />
      <PermissionSelector />
      {canDictate && <button type="button" className={`ag-iconbtn ${listening ? "is-live" : ""}`} aria-label={t(listening ? "prompt.micStop" : "prompt.mic")} aria-pressed={listening} title={t(listening ? "prompt.micStop" : "prompt.mic")} disabled={busy} onClick={dictate}><Icon name="mic" size={16} /></button>}
      <button type="button" className={`ag-send ${stopping ? "is-stop" : ""}`} aria-label={t(stopping ? "interface.stop" : working ? preferences.messageDelivery === "queue" ? "settings.addToQueue" : "settings.immediate" : "common.send")} title={t(stopping ? "interface.stop" : working ? preferences.messageDelivery === "queue" ? "settings.addToQueue" : "settings.immediate" : "common.send")} disabled={stopping ? workspace.run.status === "cancelling" : !canSend || blocked} onClick={stopping ? () => void workspace.stop() : onSubmit}><Icon name={stopping ? "stop" : "send"} size={16} /></button>
    </div>
    <p className="ag-mode-hint">{t(`studio.executeHint.${workspace.executionMode}`)}</p>
    {dictationNote && <p className="ag-prompt__note" role="status">{dictationNote}</p>}
    {workspace.uploadError && <p className="nx-upload-error" role="alert">{workspace.uploadError}</p>}
  </div></div>;
}
