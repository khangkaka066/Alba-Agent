"use client";

import { useState } from "react";
import { IntegrationsPage, type IntegrationsFilter } from "@/components/integrations/integrations-page";
import { useLocale } from "@/components/locale-provider";

const CHIPS = ["all", "mcps", "skills"] as const;
type Chip = (typeof CHIPS)[number];
const LIVE: Partial<Record<Chip, IntegrationsFilter>> = { all: "all", mcps: "mcps", skills: "skills" };

/**
 * Where the assistant is shaped: search, one chip per kind of capability, and the matching list.
 * Kinds that the platform does not provide yet say so instead of offering a button that does nothing.
 */
export function CustomizePage({ token, onConnect }: { token: string; onConnect: () => void }) {
  const { t } = useLocale();
  const [chip, setChip] = useState<Chip>("all");
  const [query, setQuery] = useState("");
  const live = LIVE[chip];
  return <div className="page-body customize-page">
    <header className="nx-page-heading"><div><h1>{t("interface.customizations")}</h1><p>{t("interface.customizationsBody")}</p></div></header>
    <label className="customize-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.2" /><path d="m15.5 15.5 4.7 4.7" /></svg>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("customize.search")} aria-label={t("customize.search")} /></label>
    <div className="customize-chips" role="tablist" aria-label={t("customize.kinds")}>
      {CHIPS.map((item) => <button key={item} type="button" role="tab" aria-selected={chip === item} className={`customize-chip ${chip === item ? "is-active" : ""}`} onClick={() => setChip(item)}>{t(`customize.${item}`)}</button>)}
    </div>
    {live
      ? <IntegrationsPage token={token} onConnect={onConnect} filter={live} query={query} bare />
      : <section className="customize-empty"><h2>{t(`customize.${chip}.title`)}</h2><p>{t(`customize.${chip}.body`)}</p><button type="button" className="button button-quiet" disabled>{t("customize.comingSoon")}</button></section>}
  </div>;
}
