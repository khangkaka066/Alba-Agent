"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon, type IconName } from "./icons";
import type { NavPage } from "./shell-context";

const SECTIONS: Array<{ page: NavPage; icon: IconName; label: string }> = [
  { page: "general", icon: "settings", label: "settings.nav.general" },
  { page: "settings", icon: "canvas", label: "settings.nav.models" },
  { page: "intelligence", icon: "review", label: "page.intelligence" },
];

/** Settings as a centred panel over the work, with its own navigation on the left, like Antigravity. Escape or a click outside closes it. */
export function SettingsModal({ page, navigate, onClose, onShortcuts, footer, children }: { page: NavPage; navigate: (page: NavPage) => void; onClose: () => void; onShortcuts: () => void; footer: ReactNode; children: ReactNode }) {
  const { t } = useLocale();
  const panel = useRef<HTMLElement>(null);
  useEffect(() => { panel.current?.focus(); }, []);
  return <div className="ag-modal" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="ag-settings" role="dialog" aria-modal="true" aria-label={t("page.settings")} tabIndex={-1} ref={panel}
      onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
      <nav className="ag-settings__nav" aria-label={t("page.settings")}>
        <h2>{t("page.settings")}</h2>
        {SECTIONS.map((section) => <button key={section.page} type="button" className={`ag-nav__item ${page === section.page ? "is-active" : ""}`} aria-current={page === section.page ? "page" : undefined} onClick={() => navigate(section.page)}><Icon name={section.icon} size={15} /><span>{t(section.label)}</span></button>)}
        <button type="button" className="ag-nav__item" onClick={onShortcuts}><Icon name="terminal" size={15} /><span>{t("shell.shortcutsTitle")}</span></button>
        <button type="button" className="ag-nav__item" onClick={() => navigate("integrations")}><Icon name="customize" size={15} /><span>{t("shell.customizations")}</span></button>
        <span className="ag-spacer" />
        <div className="ag-settings__foot">{footer}</div>
      </nav>
      <div className="ag-settings__body">
        <button type="button" className="ag-iconbtn ag-settings__close" aria-label={t("common.close")} onClick={onClose}><Icon name="close" size={16} /></button>
        {children}
      </div>
    </section>
  </div>;
}
