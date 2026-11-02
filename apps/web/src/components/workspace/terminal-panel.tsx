"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { useWorkspace } from "./workspace-context";

/** Live sandbox terminal and the virtual computer screen, fed by the run's event stream. */
export function TerminalPanel() {
  const { t } = useLocale();
  const { run, runId } = useWorkspace();
  const [tab, setTab] = useState<"terminal" | "screen">("terminal");
  const [open, setOpen] = useState(false); // collapsed until asked for: most people never need the raw output
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [run.terminal.length, open]);
  const status = run.status === "idle" ? "idle" : run.status;
  return <section className={`terminal-panel ${open ? "" : "is-collapsed"}`} aria-label="Terminal">
    <header className="terminal-head">
      <div role="tablist" aria-label="Terminal views">
        <button role="tab" aria-selected={tab === "terminal"} className={tab === "terminal" ? "is-active" : ""} onClick={() => { setTab("terminal"); setOpen(true); }}>Terminal</button>
        <button role="tab" aria-selected={tab === "screen"} className={tab === "screen" ? "is-active" : ""} onClick={() => { setTab("screen"); setOpen(true); }}>{t("terminal.screen")}</button>
      </div>
      <span className={`run-dot run-dot--${status}`} title={`Run ${status}`} />
      <span className="terminal-status">{runId ? (t(`terminal.status.${status}`) === `terminal.status.${status}` ? status : t(`terminal.status.${status}`)) : t("terminal.notRun")}</span>
      <button className="terminal-toggle" aria-label={t(open ? "terminal.collapse" : "terminal.open")} onClick={() => setOpen((value) => !value)}>{open ? "▾" : "▴"}</button>
    </header>
    {open && (tab === "terminal"
      ? <div className="terminal-body" role="log" aria-live="polite">
        {run.terminal.length === 0 ? <span className="terminal-idle">{t("terminal.idle")}</span> : run.terminal.map((line) => <div key={line.id} className={`terminal-line terminal-line--${line.stream}`}>{line.text}</div>)}
        <div ref={end} />
      </div>
      : <div className="terminal-screen">{run.frame
        // eslint-disable-next-line @next/next/no-img-element
        ? <img src={run.frame} alt="Live virtual computer screen" />
        : <span className="terminal-idle">{t("terminal.noScreen")}</span>}</div>)}
  </section>;
}
