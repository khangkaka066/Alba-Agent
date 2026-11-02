"use client";

import { useLocale } from "@/components/locale-provider";
import type { NavPage } from "@/components/studio-app";

/** Settings has two pages: models and keys, and integrations (social channels, MCP, skills). */
export function SettingsTabs({ page, onNavigate }: { page: "settings" | "integrations"; onNavigate: (page: NavPage) => void }) {
  const { t } = useLocale();
  const tabs: Array<{ id: "settings" | "integrations"; label: string }> = [{ id: "settings", label: t("settings.tab.models") }, { id: "integrations", label: t("settings.tab.integrations") }];
  return <div className="settings-tabs" role="tablist" aria-label={t("page.settings")}>
    {tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={page === tab.id} className={page === tab.id ? "is-active" : ""} onClick={() => onNavigate(tab.id)}>{tab.label}</button>)}
  </div>;
}
