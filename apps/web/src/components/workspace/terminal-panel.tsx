"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { apiRequest, readError } from "@/lib/api";
import { readSse } from "@/lib/sse";
import { RemoteScreenDialog } from "./remote-screen-dialog";
import { useComputer } from "./use-computer";
import { useWorkspace } from "./workspace-context";

/** One computer for the agent and the person: commands, stdin, processes, snapshots and a real browser. */
export function TerminalPanel({ docked = false }: { docked?: boolean }) {
  const { t } = useLocale();
  const { run, runId, token } = useWorkspace();
  const [tab, setTab] = useState<"terminal" | "screen">("terminal");
  const [openState, setOpen] = useState(false);
  const [command, setCommand] = useState("");
  const [background, setBackground] = useState(false);
  const [sending, setSending] = useState(false);
  const [controlling, setControlling] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [brokenFrame, setBrokenFrame] = useState(false);
  const [screenError, setScreenError] = useState("");
  const controlEpoch = useRef(0);
  const takeoverPending = useRef(false);
  const screenInputQueue = useRef(Promise.resolve());
  const [frame, setFrame] = useState("");
  const [checkpoint, setCheckpoint] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => { if (!copied) return; const timer = window.setTimeout(() => setCopied(false), 1500); return () => window.clearTimeout(timer); }, [copied]);
  const [clearBefore, setClearBefore] = useState(0);
  const [processesOpen, setProcessesOpen] = useState(false);
  const open = docked || openState;
  const computer = useComputer(open);
  const { computerId, session, setError } = computer;
  const active = Boolean(session?.active_process_id);
  const end = useRef<HTMLDivElement>(null);
  const screen = useRef<HTMLImageElement>(null);
  const screenTab = useRef<HTMLButtonElement>(null);
  const nearBottom = useRef(true);
  const input = useRef<HTMLInputElement>(null);
  const prefix = computerId ? `/api/v1/sandboxes/${computerId}` : "";
  const fallback = run.terminal.slice(clearBefore).map((line) => ({ ...line, sequence: 0 }));
  const lines = computerId ? computer.lines : fallback;
  useEffect(() => { if (nearBottom.current) end.current?.scrollIntoView({ block: "end" }); }, [lines.length, open]);
  useEffect(() => { setExpanded(false); setControlling(false); setFrame(""); setCheckpoint(""); setCommand(""); setClearBefore(0); }, [computerId, runId]);
  useEffect(() => {
    const selected = session?.snapshots.find((row) => row.id === checkpoint);
    if (!selected) setCheckpoint(session?.snapshots[0]?.id ?? "");
  }, [session?.snapshots, checkpoint]);
  useEffect(() => {
    if (!open || tab !== "screen" || !computerId || !token) return;
    const controller = new AbortController();
    let reconnect: number | undefined;
    const connect = async () => {
      try {
        const response = await fetch(`${prefix}/screen/stream`, { headers: { authorization: `Bearer ${token}` }, signal: controller.signal });
        await readSse(response, (_name, data) => {
          const event = JSON.parse(data) as { png_base64?: string };
          if (event.png_base64) { setFrame(`data:image/png;base64,${event.png_base64}`); setScreenError(""); }
        }, controller.signal);
      } catch (reason) { if (!controller.signal.aborted) setScreenError(readError(reason)); }
      if (!controller.signal.aborted) reconnect = window.setTimeout(() => void connect(), 1500);
    };
    void connect();
    return () => { controller.abort(); if (reconnect) window.clearTimeout(reconnect); };
  }, [open, tab, computerId, token, prefix]);

  const request = async (path: string, body: unknown = {}) => {
    setError("");
    try { return await apiRequest<Record<string, unknown>>(`${prefix}${path}`, token, { method: "POST", body: JSON.stringify(body) }); }
    catch (reason) { setError(readError(reason)); return null; }
  };
  const submit = async () => {
    if (!computerId || (!active && sending) || !command.trim()) return;
    const text = command; const waitingForExit = !active; setCommand(""); if (waitingForExit) setSending(true);
    try {
      if (active) { await computer.sendInput(`${text}\n`, session?.active_process_id); return; }
      const result = await request("/terminal", { command: text, timeout_seconds: background ? 3600 : 300, background });
      if (result?.status === "paused") setError(t("computer.approvalNeeded"));
    } catch (reason) { setError(readError(reason)); } finally { if (waitingForExit) setSending(false); input.current?.focus(); }
  };
  const setHumanControl = async (next: boolean) => {
    const epoch = ++controlEpoch.current;
    takeoverPending.current = true;
    const action = screenInputQueue.current.then(() => request("/browser", { action: "takeover", arguments: { enabled: String(next) } }));
    screenInputQueue.current = action.then(() => undefined);
    const result = await action;
    if (epoch === controlEpoch.current) {
      takeoverPending.current = false;
      if (result) { setControlling(next); if (next) screen.current?.focus(); }
    }
  };
  const takeover = () => setHumanControl(!controlling);
  const controlInput = (body: Record<string, unknown>) => {
    if (!controlling) return;
    const epoch = controlEpoch.current;
    screenInputQueue.current = screenInputQueue.current.then(async () => { if (epoch === controlEpoch.current) await request("/browser/input", body); });
  };
  const pointer = (event: React.PointerEvent<HTMLImageElement>, type: string) => {
    if (!controlling) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    controlInput({ action: "mouse", type, x: Math.max(0, Math.min(1280, (event.clientX - rect.left) / rect.width * 1280)), y: Math.max(0, Math.min(720, (event.clientY - rect.top) / rect.height * 720)) });
    event.currentTarget.focus();
  };
  const shownFrame = frame || (!computerId ? run.frame : null);
  useEffect(() => { setBrokenFrame(false); }, [shownFrame]);
  useEffect(() => { if (!controlling) return; const timer = window.setTimeout(() => setControlling(false), 300000); return () => window.clearTimeout(timer); }, [controlling]);
  const status = run.status;
  const closeRemote = () => { if (controlling || takeoverPending.current) void setHumanControl(false); setExpanded(false); };
  const screenSurface = <>        <div className="ag-screen-toolbar"><span>{t(controlling ? "computer.humanControl" : "computer.agentControl")}</span><span className="ag-spacer" />{!expanded && <button type="button" className="ag-iconbtn" aria-label={t("computer.expandScreen")} title={t("computer.expandScreen")} onClick={() => setExpanded(true)}><Icon name="expand" size={14} /></button>}<button type="button" className="ag-chip" disabled={!computerId} aria-pressed={controlling} onClick={() => void takeover()}><Icon name={controlling ? "send" : "shield"} size={13} />{t(controlling ? "computer.handBack" : "computer.takeControl")}</button></div>
        <div className={`terminal-screen ${controlling ? "is-controlled" : ""}`}>{shownFrame && !brokenFrame
          // eslint-disable-next-line @next/next/no-img-element
          ? <img ref={screen} src={shownFrame} onError={() => setBrokenFrame(true)} alt={t("computer.screenAlt")} tabIndex={controlling ? 0 : -1} role={controlling ? "application" : undefined} aria-label={controlling ? t("computer.screenKeys") : undefined} onPointerDown={(event) => pointer(event, "mousePressed")} onPointerUp={(event) => pointer(event, "mouseReleased")} onWheel={(event) => { if (!controlling) return; event.stopPropagation(); const r = event.currentTarget.getBoundingClientRect(); controlInput({ action: "mouse", type: "mouseWheel", x: (event.clientX - r.left) / r.width * 1280, y: (event.clientY - r.top) / r.height * 720, deltaX: Math.max(-5000, Math.min(5000, event.deltaX)), deltaY: Math.max(-5000, Math.min(5000, event.deltaY)) }); }} onKeyDown={(event) => { if (!controlling) return; event.stopPropagation(); if (event.key === "Escape") { event.preventDefault(); void takeover(); return; } event.preventDefault(); controlInput({ action: "key", ...(event.key.length === 1 && !event.ctrlKey && !event.metaKey ? { text: event.key } : { key: event.key, modifiers: (event.altKey ? 1 : 0) + (event.ctrlKey ? 2 : 0) + (event.metaKey ? 4 : 0) + (event.shiftKey ? 8 : 0) }) }); }} onPaste={(event) => { if (controlling) { event.preventDefault(); controlInput({ action: "key", text: event.clipboardData.getData("text").slice(0, 4096) }); } }} />
          : <div className="ag-screen-placeholder"><Icon name="globe" size={30} /><strong>{t(brokenFrame ? "computer.frameProblem" : "computer.waitingForFrame")}</strong><p>{t("computer.screenWaitingHint")}</p><button type="button" className="ag-chip" disabled={!computerId} onClick={async () => { const result = await request("/browser", { action: "screenshot", arguments: {} }); if (typeof result?.frame_png_base64 === "string") { setFrame(`data:image/png;base64,${result.frame_png_base64}`); setBrokenFrame(false); } }}>{t("computer.connectScreen")}</button></div>}</div></>;

  return <><section className={`terminal-panel ag-interactive-terminal ${open ? "" : "is-collapsed"} ${docked ? "is-docked" : ""}`} aria-label={t("dock.terminal")}>
    <header className="terminal-head">
      <div role="tablist" aria-label={t("computer.views")}>
        <button type="button" role="tab" aria-selected={tab === "terminal"} className={tab === "terminal" ? "is-active" : ""} onClick={() => { setTab("terminal"); setOpen(true); }}>{t("dock.terminal")}</button>
        <button ref={screenTab} type="button" role="tab" aria-selected={tab === "screen"} className={tab === "screen" ? "is-active" : ""} onClick={() => { setTab("screen"); setOpen(true); }}>{t("terminal.screen")}</button>
      </div>
      <span className={`run-dot run-dot--${status}`} title={status} />
      <span className="ag-spacer" />
      {open && <div className="ag-terminal-tools">
        <button type="button" className="ag-iconbtn" aria-label={t("computer.interrupt")} title={`${t("computer.interrupt")} · Ctrl+C`} disabled={!active} onClick={() => void request("/terminal/control", { action: "interrupt" })}><Icon name="stop" size={13} /></button>
        <button type="button" className="ag-iconbtn" aria-label={t("computer.restart")} title={t("computer.restart")} disabled={!computerId} onClick={() => { void request("/restart"); setControlling(false); setFrame(""); }}><Icon name="refresh" size={13} /></button>
        <button type="button" className="ag-iconbtn" aria-label={t("computer.clear")} title={t("computer.clear")} onClick={() => { computer.clear(); setClearBefore(run.terminal.length); }}><Icon name="trash" size={13} /></button>
        <button type="button" className="ag-iconbtn" aria-label={t("computer.copy")} title={t("computer.copy")} onClick={() => void navigator.clipboard.writeText(lines.map((line) => line.text).join("")).then(() => setCopied(true)).catch((reason) => setError(readError(reason)))}><Icon name={copied ? "check" : "copy"} size={13} /></button>
        <button type="button" className="ag-iconbtn" aria-label={t("computer.processes")} title={t("computer.processes")} aria-expanded={processesOpen} onClick={() => setProcessesOpen((value) => !value)}><Icon name="log" size={13} /></button>
      </div>}
      {!docked && <button type="button" className="terminal-toggle" aria-label={t(open ? "terminal.collapse" : "terminal.open")} onClick={() => setOpen((value) => !value)}>{open ? "▾" : "▴"}</button>}
    </header>
    {open && <>
      {!computerId && runId && <button type="button" className="ag-chip ag-start-computer" disabled={computer.creating} onClick={() => void computer.create()}>{t("computer.start")}</button>}
      <div className="ag-terminal-status"><code title={session?.cwd}>{session?.cwd ?? t("computer.waiting")}</code><span className="ag-spacer" />
        {session?.ports.map((port) => <button type="button" key={port} className="ag-port-button" title={t("computer.preview")} onClick={() => window.dispatchEvent(new CustomEvent("nexus:sandbox-preview", { detail: { computerId, port, force: true } }))}>:{port}</button>)}
        {session && <small title={session.resources.scope === "shell_processes" ? t("computer.processMetrics") : undefined}>CPU {session.resources.cpu_percent ?? "—"}{typeof session.resources.cpu_percent === "number" ? "%" : ""} · RAM {session.resources.memory ?? (session.resources.memory_bytes != null ? `${(session.resources.memory_bytes / 1048576).toFixed(1)} MB` : "—")}</small>}
      </div>
      {processesOpen && <div className="ag-process-list">{session?.processes.map((job) => <div key={job.id}><code title={job.command}>{job.pid} · {job.command}</code><span>{job.running ? t("computer.running") : `${t("computer.exited")} ${job.exit_code}`}</span>{job.running && <button type="button" className="ag-chip" onClick={() => void request("/terminal/control", { action: "stop", process_id: job.id })}>{t("computer.stop")}</button>}</div>)}{!session?.processes.length && <p>{t("computer.noProcesses")}</p>}</div>}
      {tab === "terminal" ? <>
        <div className="terminal-body" role="log" aria-live="off" onScroll={(event) => { const el = event.currentTarget; nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48; }}>
          {!lines.length ? <span className="terminal-idle">{t("terminal.idle")}</span> : lines.map((line, index) => <span key={`${line.sequence}-${index}`} className={`terminal-line terminal-line--${line.stream}`}>{line.text}</span>)}<div ref={end} />
        </div>
        <form className="ag-terminal-input" onSubmit={(event) => { event.preventDefault(); void submit(); }}><span aria-hidden="true">{active ? ">" : "$"}</span><input ref={input} aria-label={t(active ? "computer.stdin" : "computer.command")} placeholder={t(active ? "computer.stdinPlaceholder" : "computer.commandPlaceholder")} value={command} disabled={!computerId} autoComplete="off" spellCheck={false} onChange={(event) => setCommand(event.target.value)} onKeyDown={(event) => { if (event.ctrlKey && event.key.toLowerCase() === "c" && !window.getSelection()?.toString()) { event.preventDefault(); void request("/terminal/control", { action: "interrupt" }); } }} />
          {!active && <label title={t("computer.background")}><input type="checkbox" checked={background} onChange={(event) => setBackground(event.target.checked)} />{t("computer.backgroundShort")}</label>}<button type="submit" className="ag-iconbtn" aria-label={t("computer.send")} disabled={!computerId || (sending && !active) || !command.trim()}><Icon name="send" size={14} /></button></form>
      </> : <>
        {expanded ? <div className="ag-screen-placeholder"><Icon name="panelRight" size={20} /><span>{t("computer.remoteOpen")}</span><button type="button" className="ag-chip" onClick={() => setExpanded(false)}>{t("computer.collapseScreen")}</button></div> : screenSurface}
      </>}
      {session && session.snapshots.length > 0 && <div className="ag-terminal-snapshots"><select aria-label={t("computer.checkpoint")} value={checkpoint} onChange={(event) => setCheckpoint(event.target.value)}>{session.snapshots.map((row) => <option key={row.id} value={row.id}>{new Date(row.created_at * 1000).toLocaleTimeString()} · {row.id.slice(0, 8)}</option>)}</select><button type="button" className="ag-chip" disabled={!checkpoint || sending} onClick={async () => { setSending(true); try { await request(`/snapshots/${checkpoint}/restore`); setFrame(""); setControlling(false); } finally { setSending(false); } }}><Icon name="refresh" size={12} />{t("computer.restoreFiles")}</button></div>}
      {computer.error && <p className="ag-terminal-error" role="alert">{computer.error}</p>}
    </>}
  </section>{expanded && <RemoteScreenDialog returnFocus={screenTab} connected={Boolean(shownFrame) && !brokenFrame && !computer.error && !screenError} onClose={closeRemote}>{screenSurface}{screenError && <p className="ag-terminal-error" role="alert">{screenError}</p>}{computer.error && <p className="ag-terminal-error" role="alert">{computer.error}</p>}</RemoteScreenDialog>}</>;
}
