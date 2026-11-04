"use client";

import { LanguageSwitch } from "@/components/language-switch";
import { useLocale } from "@/components/locale-provider";
import { ShortcutSettings } from "@/components/providers/shortcut-settings";
import type { Bindings } from "@/lib/shortcuts.mjs";

/** General settings: how the app looks and reads, and the keyboard shortcuts. */
export function GeneralSettings({ theme, onTheme, bindings, onBindings, mac }: { theme: "dark" | "light"; onTheme: (value: "dark" | "light") => void; bindings: Bindings; onBindings: (next: Bindings) => void; mac: boolean }) {
  const { t } = useLocale();
  return <div className="page-body settings-page">
    <h1 className="settings-heading">{t("settings.nav.general")}</h1>
    <h2 className="settings-group-title">{t("general.appearance")}</h2>
    <div className="settings-card">
      <div className="settings-row"><div><strong>{t("general.theme")}</strong><p>{t("general.themeBody")}</p></div>
        <div className="language-switch" role="group" aria-label={t("general.theme")}>
          {(["dark", "light"] as const).map((value) => <button key={value} type="button" className={theme === value ? "is-active" : ""} aria-pressed={theme === value} onClick={() => onTheme(value)}>{t(`general.theme.${value}`)}</button>)}
        </div></div>
      <div className="settings-row"><div><strong>{t("general.language")}</strong><p>{t("general.languageBody")}</p></div><LanguageSwitch /></div>
    </div>
    <h2 className="settings-group-title">{t("shortcut.title")}</h2>
    <div className="settings-card settings-card--block"><ShortcutSettings bindings={bindings} onChange={onBindings} mac={mac} /></div>
  </div>;
}
