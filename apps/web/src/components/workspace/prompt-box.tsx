"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocale } from "@/components/locale-provider";
import { ModelPicker } from "@/components/model-picker";
import { Icon } from "@/components/shell/icons";
import { getDesktop } from "@/lib/desktop";
import { AttachmentBar, atWordStart } from "./attachments";

/** The Web Speech API where it exists. The desktop app (Electron) ships without the speech service, so it gets no microphone button. */
type Recognition = { lang: string; interimResults: boolean; continuous: boolean; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null; onend: (() => void) | null; onerror: ((event: { error: string }) => void) | null; start: () => void; stop: () => void };
type RecognitionConstructor = new () => Recognition;
function recognitionClass(): RecognitionConstructor | null {
  if (typeof window === "undefined" || getDesktop()) return null;
  const scope = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

/** Permission preset. Read-only on purpose: the policy is fixed by the sandbox (deny, ask, allow), and this says what it does. */
function PermissionChip() {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", escape); };
  }, [open]);
  return <span className="ag-popwrap" ref={root}>
    <button type="button" className="ag-chip" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((value) => !value)}><Icon name="shield" size={14} />{t("perm.auto")}<Icon name="chevronDown" size={12} /></button>
    {open && <div className="ag-popover ag-popover--up" role="dialog" aria-label={t("perm.title")}>
      <strong>{t("perm.title")}</strong>
      <p>{t("perm.body")}</p>
      <ul><li>{t("perm.allow")}</li><li>{t("perm.ask")}</li><li>{t("perm.deny")}</li></ul>
      <small>{t("perm.keys")}</small>
    </div>}
  </span>;
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
  /** Extra controls placed after the model picker (folder chip, scale). */
  children?: ReactNode;
  /** Called when "/" is typed at the start of a word: the owner decides what to open. */
  onSlash?: () => void;
};

/** The message box of Antigravity: one rounded box with attach, model, permissions, dictation and send. Shared by the home screen and the conversation. */
export function PromptBox({ value, onChange, onSubmit, onOpenSettings, placeholder, busy, canSend, rows = 2, autoFocus, label, children, onSlash }: Props) {
  const { t, locale } = useLocale();
  const [picking, setPicking] = useState(false);
  const [listening, setListening] = useState(false);
  const [dictationNote, setDictationNote] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);
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

  return <div className="ag-prompt">
    <textarea ref={field} aria-label={label} rows={rows} autoFocus={autoFocus} value={value} disabled={busy} placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.nativeEvent.isComposing) return;
        if (event.key === "@" && atWordStart(event.currentTarget)) { event.preventDefault(); setPicking(true); return; }
        if (event.key === "/" && onSlash && atWordStart(event.currentTarget) && value.trim() === "") { event.preventDefault(); onSlash(); return; }
        if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSubmit(); }
      }} />
    <AttachmentBar open={picking} onOpenChange={setPicking} />
    <div className="ag-prompt__bar">
      <button type="button" className="ag-iconbtn" aria-label={t("prompt.attach")} title={t("prompt.attach")} disabled={busy} onClick={() => setPicking(true)}><Icon name="plus" size={16} /></button>
      <ModelPicker compact disabled={busy} onOpenSettings={onOpenSettings} />
      {children}
      <span className="ag-spacer" />
      <PermissionChip />
      {canDictate && <button type="button" className={`ag-iconbtn ${listening ? "is-live" : ""}`} aria-label={t(listening ? "prompt.micStop" : "prompt.mic")} aria-pressed={listening} title={t(listening ? "prompt.micStop" : "prompt.mic")} disabled={busy} onClick={dictate}><Icon name="mic" size={16} /></button>}
      <button type="button" className="ag-send" aria-label={t("common.send")} title={t("common.send")} disabled={!canSend || busy} onClick={onSubmit}><Icon name="send" size={16} /></button>
    </div>
    {dictationNote && <p className="ag-prompt__note" role="status">{dictationNote}</p>}
  </div>;
}
