"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { useModels } from "@/components/model-context";
import { loadRecent, modelLabel, parseModelId, pickerView, rememberRecent } from "@/lib/models.mjs";

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
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showCustom, setShowCustom] = useState(false);
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

  const view = pickerView(models, recent, query);
  const lockedProviders = new Set(suggested.filter((item) => !item.connected).map((item) => item.provider)).size;
  const pick = (id: string) => { choose(id); rememberRecent(window.localStorage, id); setOpen(false); setCustom(""); setProblem(""); setQuery(""); setShowCustom(false); };
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
        setRecent(loadRecent(window.localStorage)); setExpanded(selected ? models.find((item) => item.id === selected)?.group ?? null : null);
        setOpen((value) => !value); setProblem(""); setQuery("");
      }}>
      <span className="model-trigger__dot" /><span className="model-trigger__name">{missing ? t("pill.add") : modelLabel(selected)}</span>
      <svg className="model-trigger__chevron" viewBox="0 0 12 12" aria-hidden="true"><path d="m3 4.5 3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
    {open && <div className={`model-menu ${place.up ? "model-menu--up" : ""}`} style={{ maxHeight: place.room }} role="dialog" aria-label={t("model.choose")}>
      <input className="model-menu__search" autoFocus value={query} spellCheck={false} placeholder={t("model.search")} aria-label={t("model.search")} onChange={(event) => setQuery(event.target.value)} />
      <div role="listbox" aria-label={t("model.choose")}>
        {(() => {
          const item = (model: (typeof models)[number], label = model.model) => <button type="button" role="option" aria-selected={model.id === selected} key={model.id} className={`model-menu__item ${model.id === selected ? "is-selected" : ""}`} onClick={() => pick(model.id)}>
            <span>{label}</span>{model.unverified && <span className="model-menu__badge model-menu__badge--warn" title={t("model.unverified")}>{t("model.unverified")}</span>}{model.id === selected && <span aria-hidden="true">✓</span>}</button>;
          if (query.trim()) return view.matches.length ? view.matches.map((model) => item(model, `${model.group} · ${model.model}`)) : <p className="model-menu__hint">{t("model.noMatch")}</p>;
          return <>
            {view.recent.length > 0 && <div className="model-menu__group" role="group" aria-label={t("model.recent")}><h4>{t("model.recent")}</h4>{view.recent.map((model) => item(model, `${model.group} · ${model.model}`))}</div>}
            <div className="model-menu__group" role="group" aria-label={t("model.providers")}><h4>{t("model.providers")}</h4>
              {view.providers.map((group) => <div key={group.name}>
                <button type="button" className="model-menu__provider" aria-expanded={expanded === group.name} onClick={() => setExpanded(expanded === group.name ? null : group.name)}>
                  <span>{group.name}{group.local && <span className="model-menu__badge">{t("model.local")}</span>}</span><span className="model-menu__count">{group.models.length}</span></button>
                {expanded === group.name && group.models.map((model) => item(model))}
              </div>)}
            </div>
          </>;
        })()}
      </div>
      {showCustom
        ? <form className="model-menu__custom" onSubmit={(event) => { event.preventDefault(); submitCustom(); }}>
            <label htmlFor={compact ? "model-custom-compact" : "model-custom"}>{t("model.custom")}</label>
            <div><input id={compact ? "model-custom-compact" : "model-custom"} value={custom} spellCheck={false} autoComplete="off" placeholder={t("model.customPlaceholder")} onChange={(event) => { setCustom(event.target.value); setProblem(""); }} />
              <button type="submit" disabled={!custom.trim()}>{t("model.useCustom")}</button></div>
            {problem && <p className="model-menu__problem" role="alert">{problem}</p>}
          </form>
        : <button type="button" className="model-menu__footer" onClick={() => setShowCustom(true)}>{t("model.custom")}…</button>}
      <button type="button" className="model-menu__footer" onClick={() => { setOpen(false); onOpenSettings(); }}>{lockedProviders > 0 ? t("model.manageWithLocked", { count: lockedProviders }) : t("model.manage")}</button>
    </div>}
  </div>;
}
