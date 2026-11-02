"use client";

import { LOCALES } from "@/lib/i18n.mjs";
import { useLocale } from "@/components/locale-provider";

/** Two-button language toggle; the active language is the pressed one. */
export function LanguageSwitch() {
  const { locale, setLocale, t } = useLocale();
  return <div className="language-switch" role="group" aria-label={t("language.label")}>
    {LOCALES.map((item) => <button key={item.id} type="button" className={item.id === locale ? "is-active" : ""} aria-pressed={item.id === locale} title={item.label} onClick={() => setLocale(item.id)}>{item.id.toUpperCase()}</button>)}
  </div>;
}
