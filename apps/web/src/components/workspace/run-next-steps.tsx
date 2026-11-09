"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { useWorkspace } from "./workspace-context";

export function RunNextSteps() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [open, setOpen] = useState(false);
  const [packing, setPacking] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => { setOpen(false); trigger.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus();
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", escape); };
  }, [open]);
  const move = (event: React.KeyboardEvent) => {
    const buttons = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? []);
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      buttons[(index + (event.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus();
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault(); buttons[event.key === "Home" ? 0 : buttons.length - 1]?.focus();
    } else if (event.key === "Tab") setOpen(false);
  };
  const handoff = (studioId: string, key: string) => { setOpen(false); workspace.setExecutionMode("agent"); void workspace.startTask(t(key), "standard", { studioId, executionMode: "agent" }); };
  return <div ref={root} className="ag-next-steps">
    <button ref={trigger} type="button" className="ag-chip" aria-haspopup="menu" aria-expanded={open} onClick={() => open ? close() : setOpen(true)} onKeyDown={(event) => { if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); } }}>{t("result.continue")}<Icon name="chevronDown" size={13} /></button>
    {open && <div role="menu" aria-label={t("result.continue")} onKeyDown={move}>
      <button type="button" role="menuitem" disabled={workspace.busy} onClick={() => handoff("marketing-social-publishing-studio", "handoff.marketingPrompt")}><Icon name="send" size={14} />{t("result.marketing")}</button>
      <button type="button" role="menuitem" disabled={workspace.busy} onClick={() => handoff("analytics-optimization-studio", "handoff.analyticsPrompt")}><Icon name="canvas" size={14} />{t("result.analytics")}</button>
      <button type="button" role="menuitem" disabled={packing} onClick={async () => { setPacking(true); try { await workspace.downloadAll(); setOpen(false); } finally { setPacking(false); } }}><Icon name="chevronDown" size={14} />{t(packing ? "studio.packing" : "result.zip")}</button>
    </div>}
  </div>;
}
