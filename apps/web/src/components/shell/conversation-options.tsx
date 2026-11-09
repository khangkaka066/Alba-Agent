"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useLocale } from "@/components/locale-provider";
import { loadSidebar, normalizeSidebar, saveSidebar, SIDEBAR_DEFAULTS, type SidebarState } from "@/lib/sidebar-view.mjs";
import { Icon } from "./icons";

export function useSidebarPreferences(scope: string) {
  const key = scope ? `alba_sidebar_view:${scope}` : "";
  const [stored, setStored] = useState({ key: "", value: normalizeSidebar(null) });
  useEffect(() => {
    if (!key) return;
    setStored({ key, value: loadSidebar(window.localStorage, key) });
    const sync = (event: StorageEvent) => { if (event.key === key) setStored({ key, value: loadSidebar(window.localStorage, key) }); };
    window.addEventListener("storage", sync); return () => window.removeEventListener("storage", sync);
  }, [key]);
  useEffect(() => { if (key && stored.key === key) saveSidebar(window.localStorage, key, stored.value); }, [stored, key]);
  const update = useCallback((change: Partial<SidebarState> | ((value: SidebarState) => SidebarState)) => {
    setStored(previous => {
      const value = previous.key === key ? previous.value : normalizeSidebar(null);
      const next = typeof change === "function" ? change(value) : { ...value, ...change };
      return next === value && previous.key === key ? previous : { key, value: normalizeSidebar(next) };
    });
  }, [key]);
  return { state: stored.key === key ? stored.value : SIDEBAR_DEFAULTS, update, ready: Boolean(key && stored.key === key) };
}

type PopupProps = { anchor: HTMLElement; onClose: () => void; children: ReactNode; label: string; className?: string };
export function SidebarPopup({ anchor, onClose, children, label, className = "" }: PopupProps) {
  const root = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 8, top: 8, submenuLeft: 298 });
  useEffect(() => {
    const place = () => { const a = anchor.getBoundingClientRect(), r = root.current?.getBoundingClientRect(); const width = r?.width || 296; const left = Math.max(8, Math.min(a.left, innerWidth - width - 8)); setPosition({ left, top: Math.max(8, Math.min(a.bottom + 6, innerHeight - (r?.height || 340) - 8)), submenuLeft: left + width + 234 > innerWidth ? -232 : width + 2 }); };
    place(); const frame = requestAnimationFrame(() => root.current?.querySelector<HTMLElement>('[role^="menuitem"]:not(:disabled)')?.focus());
    const away = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node) && !anchor.contains(event.target as Node)) onClose(); };
    const resize = () => onClose();
    document.addEventListener("pointerdown", away); window.addEventListener("resize", resize);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("pointerdown", away); window.removeEventListener("resize", resize); };
  }, [anchor, onClose]);
  const close = () => { onClose(); if (anchor.isConnected) anchor.focus(); };
  const host = typeof document !== "undefined" ? document.querySelector(".ag-app") : null;
  return host ? createPortal(<div ref={root} className={`nx-sidebar-popup ${className}`} style={{ left: position.left, top: position.top, "--popup-top": `${position.top}px`, "--submenu-left": `${position.submenuLeft}px` } as React.CSSProperties} role="menu" aria-label={label} onKeyDown={event => {
    if (event.key === "Escape" || event.key === "Tab") { if (event.key === "Escape") event.preventDefault(); event.stopPropagation(); close(); return; }
    if ((event.target as HTMLElement).tagName === "INPUT") return;
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      const panel = (event.target as HTMLElement).closest('[role="menu"]') ?? event.currentTarget;
      const items = [...panel.querySelectorAll<HTMLElement>('[role^="menuitem"]:not(:disabled)')].filter(item => item.closest('[role="menu"]') === panel && item.getClientRects().length > 0);
      if (!items.length) return;
      event.preventDefault(); const at = items.indexOf(document.activeElement as HTMLElement);
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (at + (event.key === "ArrowUp" ? items.length - 1 : 1)) % items.length]?.focus();
    }
  }}>{children}</div>, host) : null;
}

type OptionsProps = { state: SidebarState; update: (value: Partial<SidebarState>) => void; unreadCount: number; markAllRead: () => void; disabled?: boolean };
type Panel = "group" | "conversations" | "projects" | "filter" | "display";
export function ConversationOptions({ state, update, unreadCount, markAllRead, disabled }: OptionsProps) {
  const { t } = useLocale();
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<{ id: Panel; top: number } | null>(null);
  const close = useCallback(() => { setOpen(false); setPanel(null); }, []);
  const select = (value: Partial<SidebarState>) => { update(value); close(); trigger.current?.focus(); };
  const show = (id: Panel, button: HTMLElement, focus = false) => {
    setPanel({ id, top: button.offsetTop });
    if (focus) requestAnimationFrame(() => document.querySelector<HTMLElement>('.nx-sidebar-submenu .nx-sidebar-menu-row')?.focus());
  };
  const back = () => { const id = panel?.id; setPanel(null); requestAnimationFrame(() => document.querySelector<HTMLElement>(`.nx-sidebar-popup [data-submenu="${id}"]`)?.focus()); };
  const parent = (id: Panel, label: string, value?: string) => <button type="button" className="nx-sidebar-menu-row" role="menuitem" aria-haspopup="menu" aria-expanded={panel?.id === id} data-submenu={id} onMouseEnter={event => show(id, event.currentTarget)} onClick={event => show(id, event.currentTarget, true)} onKeyDown={event => { if (event.key === "ArrowRight") { event.preventDefault(); show(id, event.currentTarget, true); } }}><span>{label}</span>{value && <span className="nx-sidebar-menu-value">{value}</span>}<Icon name="chevronRight" size={14} /></button>;
  const check = (label: string, checked: boolean, run: () => void) => <button type="button" className="nx-sidebar-menu-row" role="menuitemcheckbox" aria-checked={checked} onMouseEnter={() => setPanel(null)} onClick={() => { run(); close(); trigger.current?.focus(); }}><span>{label}</span>{checked && <Icon name="check" size={14} />}</button>;
  const radio = (label: string, checked: boolean, value: Partial<SidebarState>) => <button type="button" className="nx-sidebar-menu-row" role="menuitemradio" aria-checked={checked} onClick={() => select(value)}><span>{label}</span>{checked && <Icon name="check" size={14} />}</button>;
  const toggle = (label: string, checked: boolean, value: Partial<SidebarState>) => <button type="button" className="nx-sidebar-menu-row" role="menuitemcheckbox" aria-checked={checked} onClick={() => select(value)}><span>{label}</span>{checked && <Icon name="check" size={14} />}</button>;
  const filtered = state.filter !== "all" || Boolean(state.query) || state.archivedOnly;
  return <><button ref={trigger} type="button" className={`ag-iconbtn ag-iconbtn--small nx-sidebar-options-trigger ${filtered ? "has-filter" : ""}`} aria-label={t("sidebar.options")} title={t("sidebar.options")} aria-haspopup="menu" aria-expanded={open} disabled={disabled} onClick={() => open ? close() : setOpen(true)}><Icon name="filter" size={14} /></button>
    {open && trigger.current && <SidebarPopup anchor={trigger.current} onClose={close} label={t("sidebar.options")}>
      {parent("group", t("sidebar.groupBy"), t(`sidebar.group.${state.groupBy}`))}
      {parent("conversations", t("sidebar.sortConversations"), t(`sidebar.sort.${state.conversationSort}`))}
      {parent("projects", t("sidebar.sortProjects"), t(`sidebar.sort.${state.projectSort}`))}
      <div role="separator" className="nx-sidebar-menu-separator" />
      {parent("filter", t("sidebar.filter"))}{parent("display", t("sidebar.display"))}
      {check(t("sidebar.autoPin"), state.autoPin, () => update({ autoPin: !state.autoPin }))}
      {check(t("sidebar.archivedOnly"), state.archivedOnly, () => update({ archivedOnly: !state.archivedOnly }))}
      <div role="separator" className="nx-sidebar-menu-separator" />
      <button type="button" className="nx-sidebar-menu-row" role="menuitem" disabled={!unreadCount} onMouseEnter={() => setPanel(null)} onClick={() => { markAllRead(); close(); trigger.current?.focus(); }}>{t("sidebar.markAllRead")}</button>
      {panel && <div className="nx-sidebar-submenu" role="menu" aria-label={t(panel.id === "group" ? "sidebar.groupBy" : panel.id === "conversations" ? "sidebar.sortConversations" : panel.id === "projects" ? "sidebar.sortProjects" : `sidebar.${panel.id}`)} style={{ "--submenu-top": `${Math.min(panel.top, 116)}px` } as React.CSSProperties} onKeyDown={event => { if (event.key === "ArrowLeft") { event.preventDefault(); event.stopPropagation(); back(); } }}>
        <button type="button" className="nx-sidebar-menu-back" role="menuitem" onClick={back}><Icon name="back" size={14} />{t("sidebar.back")}</button>
        {panel.id === "group" && (["project", "none"] as const).map(value => <div key={value}>{radio(t(`sidebar.group.${value}`), state.groupBy === value, { groupBy: value })}</div>)}
        {panel.id === "conversations" && (["updated", "created", "name"] as const).map(value => <div key={value}>{radio(t(`sidebar.sort.${value}`), state.conversationSort === value, { conversationSort: value })}</div>)}
        {panel.id === "projects" && (["custom", "updated", "name"] as const).map(value => <div key={value}>{radio(t(`sidebar.sort.${value}`), state.projectSort === value, { projectSort: value })}</div>)}
        {panel.id === "filter" && <><input type="search" className="nx-sidebar-menu-search" value={state.query} placeholder={t("sidebar.search")} aria-label={t("sidebar.search")} onChange={event => update({ query: event.target.value })} />{(["all", "active", "attention", "completed", "unread"] as const).map(value => <div key={value}>{radio(t(`sidebar.filter.${value}`), state.filter === value, { filter: value })}</div>)}</>}
        {panel.id === "display" && <>{toggle(t("sidebar.display.time"), state.showTime, { showTime: !state.showTime })}{toggle(t("sidebar.display.status"), state.showStatus, { showStatus: !state.showStatus })}<div role="separator" className="nx-sidebar-menu-separator" />{radio(t("sidebar.display.compact"), state.compact, { compact: true })}{radio(t("sidebar.display.comfortable"), !state.compact, { compact: false })}</>}
      </div>}
    </SidebarPopup>}
  </>;
}
