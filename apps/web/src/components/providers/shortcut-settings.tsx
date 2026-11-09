"use client";

import { useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { ACTIONS, DEFAULT_BINDINGS, comboFromEvent, findConflict, formatCombo, isValidCombo, type Bindings } from "@/lib/shortcuts.mjs";

export function ShortcutSettings({ bindings, onChange, mac }: { bindings: Bindings; onChange: (next: Bindings) => void; mac: boolean }) {
  const { t } = useLocale();
  const [recording, setRecording] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const labelOf = (id: string) => t(`shortcut.${id}`);
  const customised = ACTIONS.some((action) => bindings[action.id] !== DEFAULT_BINDINGS[action.id]);

  const capture = (event: React.KeyboardEvent<HTMLButtonElement>, id: string) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Escape") { setRecording(null); setMessage(""); return; }
    const combo = comboFromEvent(event.nativeEvent);
    if (!combo) return;
    if (!isValidCombo(combo)) { setMessage(t("shortcut.needModifier", { modifier: mac ? "⌘" : "Ctrl" })); return; }
    const conflict = findConflict(bindings, id, combo);
    if (conflict) { setMessage(t("shortcut.conflict", { combo: formatCombo(combo, mac), action: labelOf(conflict) })); return; }
    onChange({ ...bindings, [id]: combo });
    setRecording(null); setMessage("");
  };

  return <section className="shortcut-settings nx-settings-page" aria-label={t("shortcut.title")}>
    <header className="nx-settings-heading"><h1>{t("settings.nav.shortcuts")}</h1><p>{t("settings.shortcuts.description")}</p></header>
    <label className="nx-shortcut-search"><input type="search" aria-label={t("settings.searchShortcuts")} placeholder={t("settings.searchShortcuts")} value={query} onChange={event=>setQuery(event.target.value)} /></label>
    <button type="button" className="nx-settings-advanced" disabled={!customised} onClick={() => { onChange({ ...DEFAULT_BINDINGS }); setRecording(null); setMessage(""); }}>{t("shortcut.resetAll")}</button>
    {message && <div className="provider-alert provider-alert--error" role="alert">{message}</div>}
    {["general", "navigation"].map((group) => <div className="shortcut-group" key={group}>
      <h3>{t(`shortcut.group.${group}`)}</h3>
      {ACTIONS.filter((action) => action.group === group && labelOf(action.id).toLowerCase().includes(query.toLowerCase())).map((action) => {
        const isRecording = recording === action.id;
        const changed = bindings[action.id] !== action.default;
        return <div className="shortcut-row" key={action.id}>
          <span>{labelOf(action.id)}</span>
          <span className="shortcut-keys">
            <button className={`shortcut-chip ${isRecording ? "is-recording" : ""}`} data-shortcut-capture={isRecording ? "1" : undefined} aria-label={t("shortcut.change", { action: labelOf(action.id) })} autoFocus={isRecording}
              onClick={() => { setRecording(action.id); setMessage(""); }} onBlur={() => { if (isRecording) { setRecording(null); setMessage(""); } }}
              onKeyDown={isRecording ? (event) => capture(event, action.id) : undefined}>
              {isRecording ? t("shortcut.press") : formatCombo(bindings[action.id], mac) || t("settings.unassigned")}
            </button>
            <button type="button" className="ag-iconbtn" aria-label={t("settings.removeShortcut", { name: labelOf(action.id) })} onClick={() => onChange({ ...bindings, [action.id]: "" })}>×</button>
            {changed && <button className="button button-quiet shortcut-reset" onClick={() => onChange({ ...bindings, [action.id]: action.default })}>{t("shortcut.reset")}</button>}
          </span>
        </div>;
      })}
    </div>)}
  </section>;
}
