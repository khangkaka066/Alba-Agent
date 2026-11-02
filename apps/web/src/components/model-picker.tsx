"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { useModels } from "@/components/model-context";
import { groupModels, modelLabel, parseModelId } from "@/lib/models.mjs";

/**
 * Dropdown that shows the active model and switches it. It always opens: connected models first, then well-known models
 * (usable once their provider has a key), then a box for any model id. `compact` is the small pill inside a prompt bar.
 */
export function ModelPicker({ compact = false, disabled = false, onOpenSettings }: { compact?: boolean; disabled?: boolean; onOpenSettings: () => void }) {
  const { t } = useLocale();
  const { models, suggested, reachable, selected, loading, choose, refresh } = useModels();
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState("");
  const [problem, setProblem] = useState("");
  const [place, setPlace] = useState<{ up: boolean; room: number }>({ up: false, room: 560 });
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    void refresh();
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.stopPropagation(); setOpen(false); } };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape, true);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", escape, true); };
  }, [open, refresh]);

  if (loading) return <span className={`model-picker model-picker--idle ${compact ? "model-picker--compact" : ""}`} aria-hidden="true" />;

  const groups = groupModels(models);
  const pick = (id: string) => { choose(id); setOpen(false); setCustom(""); setProblem(""); };
  const submitCustom = () => {
    const parsed = parseModelId(custom);
    if (!parsed) { setProblem(t("model.customInvalid")); return; }
    if (!reachable.includes(parsed.provider)) { setProblem(t("model.customNoProvider", { provider: parsed.provider })); return; }
    pick(parsed.id);
  };
  const missing = selected === null;
  return <div className={`model-picker ${compact ? "model-picker--compact" : ""}`} ref={root}>
    <button type="button" className={`model-trigger ${missing ? "model-trigger--missing" : ""} ${compact ? "model-trigger--compact" : ""}`} disabled={disabled} aria-haspopup="dialog" aria-expanded={open}
      title={missing ? t("pill.titleAdd") : t("model.current", { model: modelLabel(selected) })} onClick={() => {
        // Open towards the side with more room, and never taller than that room, so the custom-id box is always reachable.
        const rect = root.current?.getBoundingClientRect();
        if (rect) { const above = rect.top - 12, below = window.innerHeight - rect.bottom - 12; const up = compact && above > below; setPlace({ up, room: Math.max(220, Math.min(560, up ? above : below)) }); }
        setOpen((value) => !value); setProblem("");
      }}>
      <span className="model-trigger__dot" /><span className="model-trigger__name">{missing ? t("pill.add") : modelLabel(selected)}</span>
      <svg className="model-trigger__chevron" viewBox="0 0 12 12" aria-hidden="true"><path d="m3 4.5 3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    {open && <div className={`model-menu ${place.up ? "model-menu--up" : ""}`} style={{ maxHeight: place.room }} role="dialog" aria-label={t("model.choose")}>
      <p className="model-menu__hint">{t("model.forNext")}</p>
      <div role="listbox" aria-label={t("model.choose")}>
        {groups.map((group) => <div className="model-menu__group" key={group.name} role="group" aria-label={group.name}>
          <h4>{group.name}{group.local && <span className="model-menu__badge">{t("model.local")}</span>}</h4>
          {group.models.map((model) => <button type="button" role="option" aria-selected={model.id === selected} key={model.id} className={`model-menu__item ${model.id === selected ? "is-selected" : ""}`} onClick={() => pick(model.id)}>
            <span>{model.model}</span>{model.id === selected && <span aria-hidden="true">✓</span>}
          </button>)}
        </div>)}
        {suggested.length > 0 && <div className="model-menu__group" role="group" aria-label={t("model.suggested")}>
          <h4>{t("model.suggested")}</h4>
          {suggested.map((model) => <button type="button" role="option" aria-selected={model.id === selected} aria-disabled={!model.connected} key={model.id}
            className={`model-menu__item ${model.id === selected ? "is-selected" : ""} ${model.connected ? "" : "is-locked"}`}
            title={model.connected ? undefined : t("model.needsKey", { provider: model.group })} onClick={() => { if (model.connected) pick(model.id); else setProblem(t("model.customNoProvider", { provider: model.group })); }}>
            <span>{model.provider}/{model.model}</span>{model.id === selected ? <span aria-hidden="true">✓</span> : !model.connected && <span className="model-menu__lock">{t("model.needsKeyShort")}</span>}
          </button>)}
        </div>}
      </div>
      <form className="model-menu__custom" onSubmit={(event) => { event.preventDefault(); submitCustom(); }}>
        <label htmlFor={compact ? "model-custom-compact" : "model-custom"}>{t("model.custom")}</label>
        <div><input id={compact ? "model-custom-compact" : "model-custom"} value={custom} spellCheck={false} autoComplete="off" placeholder={t("model.customPlaceholder")} onChange={(event) => { setCustom(event.target.value); setProblem(""); }} />
          <button type="submit" disabled={!custom.trim()}>{t("model.useCustom")}</button></div>
        {problem && <p className="model-menu__problem" role="alert">{problem}</p>}
      </form>
      <button type="button" className="model-menu__footer" onClick={() => { setOpen(false); onOpenSettings(); }}>{t("model.manage")}</button>
    </div>}
  </div>;
}
