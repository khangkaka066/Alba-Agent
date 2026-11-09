"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { useModels } from "@/components/model-context";
import { Icon } from "@/components/shell/icons";
import { apiRequest, readError } from "@/lib/api";
import { dateLocale, statusLabel } from "@/lib/i18n.mjs";
import { MessageContent } from "@/components/workspace/message-content";

type Scope = { tenant_id: string; workspace_id: string };
type Bot = { id: string; name: string; model: string };
type Routine = Scope & { id: string; bot_id: string; name: string; instruction_markdown: string; cron_expression: string; timezone: string; enabled: boolean; workflow_id: string | null; interval_seconds: number | null };
type RoutineRun = { id: string; status: string; created_at: string; result: string };

export function ScheduledTasks({ token, scope, onManageAgents }: { token: string; scope: Scope; onManageAgents: () => void }) {
  const { t, locale } = useLocale();
  const { selected } = useModels();
  const [tasks, setTasks] = useState<Routine[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [history, setHistory] = useState<Routine | null>(null);
  const [runs, setRuns] = useState<RoutineRun[] | null>(null);
  const [draft, setDraft] = useState({ name: "", instruction_markdown: "", bot_id: "", cron_expression: "0 9 * * *", timezone: "Asia/Ho_Chi_Minh" });
  const load = useCallback(async () => {
    if (!token) return;
    try { const [routines, agents] = await Promise.all([apiRequest<Routine[]>("/api/v1/routines", token), apiRequest<Bot[]>("/api/v1/bots", token)]); setTasks(routines); setBots(agents); }
    catch (reason) { setError(readError(reason)); } finally { setLoading(false); }
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!history) return;
    let stopped = false; setRuns(null);
    const refresh = () => void apiRequest<RoutineRun[]>(`/api/v1/routines/${history.id}/runs`, token).then((value) => { if (!stopped) setRuns(value); }).catch((reason) => { if (!stopped) setError(readError(reason)); });
    refresh(); const timer = window.setInterval(refresh, 4000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [history, token]);
  useEffect(() => {
    if (!editing && !history) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) { setEditing(false); setHistory(null); } };
    document.addEventListener("keydown", escape); return () => document.removeEventListener("keydown", escape);
  }, [editing, history, busy]);
  const save = async () => {
    setBusy(true); setError("");
    try {
      let botId = draft.bot_id;
      if (!botId) {
        if (!selected) throw new Error(t("schedule.chooseModel"));
        botId = crypto.randomUUID();
        const agent = await apiRequest<Bot>("/api/v1/bots", token, { method: "POST", body: JSON.stringify({ id: botId, ...scope, name: draft.name.trim(), description: "", model: selected, memory_namespace: `nexus:routines:${botId}`, tool_ids: [], billing_mode: "platform" }) });
        setBots((current) => [...current, agent]); setDraft((current) => ({ ...current, bot_id: agent.id }));
      }
      const original = editingId ? tasks.find((item) => item.id === editingId) : null;
      await apiRequest<Routine>(editingId ? `/api/v1/routines/${editingId}` : "/api/v1/routines", token, { method: editingId ? "PUT" : "POST", body: JSON.stringify({ ...scope, ...(original ?? {}), ...draft, bot_id: botId, id: editingId ?? crypto.randomUUID(), enabled: original?.enabled ?? true }) });
      setEditing(false); setSaved(true); await load();
    } catch (reason) { setError(readError(reason)); } finally { setBusy(false); }
  };
  const toggle = async (task: Routine) => {
    setBusy(true); setError("");
    try { const value = await apiRequest<Routine>(`/api/v1/routines/${task.id}`, token, { method: "PUT", body: JSON.stringify({ ...task, enabled: !task.enabled }) }); setTasks((current) => current.map((item) => item.id === value.id ? value : item)); }
    catch (reason) { setError(readError(reason)); } finally { setBusy(false); }
  };
  const run = async (task: Routine) => {
    setBusy(true); setError("");
    try { await apiRequest(`/api/v1/routines/${task.id}/runs`, token, { method: "POST" }); setHistory(task); }
    catch (reason) { setError(readError(reason)); } finally { setBusy(false); }
  };
  const schedule = (task: Routine) => task.interval_seconds ? t("schedule.interval", { seconds: task.interval_seconds }) : t(task.cron_expression === "0 9 * * *" ? "schedule.daily" : task.cron_expression === "0 9 * * 1-5" ? "schedule.weekdays" : task.cron_expression === "0 9 * * 1" ? "schedule.weekly" : "schedule.custom");
  return <div className="nx-schedules">
    <header className="nx-page-heading"><div><h1>{t("interface.scheduledTasks")}</h1><p>{t("schedule.intro")}</p></div><button type="button" className="button button-primary" onClick={() => { setEditingId(null); setDraft({ name: "", instruction_markdown: "", bot_id: bots[0]?.id ?? "", cron_expression: "0 9 * * *", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }); setError(""); setEditing(true); }}><Icon name="plus" size={14} />{t("schedule.new")}</button></header>
    {error && <p className="ag-problem" role="alert">{error}</p>}
    {saved && <p className="nx-saved" role="status">{t("schedule.saved")}</p>}
    {loading ? <p className="ag-empty">{t("common.loading")}</p> : tasks.length === 0 ? <div className="nx-schedule-empty"><Icon name="log" size={28} /><h2>{t("schedule.empty")}</h2><p>{t("schedule.emptyBody")}</p></div> : <div className="nx-schedule-table"><table><thead><tr><th>{t("schedule.task")}</th><th>{t("schedule.schedule")}</th><th>{t("schedule.agent")}</th><th>{t("schedule.enabled")}</th><th><span className="sr-only">{t("schedule.actions")}</span></th></tr></thead><tbody>{tasks.map((task) => <tr key={task.id}><td><button type="button" className="nx-task-name" onClick={() => setHistory(task)}>{task.name}</button><small>{task.instruction_markdown.slice(0, 100)}</small></td><td>{schedule(task)}<small>{task.timezone}</small><code>{task.cron_expression}</code></td><td>{bots.find((bot) => bot.id === task.bot_id)?.name ?? t("schedule.agentName")}</td><td><button type="button" className="nx-switch" role="switch" aria-checked={task.enabled} aria-label={t("schedule.enableTask", { name: task.name })} disabled={busy} onClick={() => void toggle(task)}><i /></button></td><td><div className="nx-task-actions"><button type="button" className="button button-quiet" disabled={busy || !task.enabled} onClick={() => void run(task)}>{t("schedule.runNow")}</button><button type="button" className="ag-iconbtn" title={t("schedule.edit")} aria-label={t("schedule.edit")} onClick={() => { setEditingId(task.id); setDraft({ name: task.name, instruction_markdown: task.instruction_markdown, bot_id: task.bot_id, cron_expression: task.cron_expression, timezone: task.timezone }); setEditing(true); }}><Icon name="review" /></button><button type="button" className="ag-iconbtn" title={t("schedule.history")} aria-label={t("schedule.history")} onClick={() => setHistory(task)}><Icon name="log" /></button></div></td></tr>)}</tbody></table></div>}
    <footer><button type="button" className="button button-quiet" onClick={onManageAgents}><Icon name="settings" size={14} />{t("schedule.manageAgents")}</button></footer>
    {editing && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setEditing(false); }}><form className="modal-card nx-schedule-dialog" role="dialog" aria-modal="true" aria-label={t(editingId ? "schedule.edit" : "schedule.new")} onSubmit={(event) => { event.preventDefault(); if (draft.name.trim() && draft.instruction_markdown.trim()) void save(); }}><header><h2>{t(editingId ? "schedule.edit" : "schedule.new")}</h2><button type="button" className="ag-iconbtn" aria-label={t("common.close")} onClick={() => setEditing(false)} disabled={busy}><Icon name="close" /></button></header>
      <label className="field"><span>{t("schedule.name")}</span><input autoFocus required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
      <label className="field"><span>{t("schedule.instructions")}</span><textarea rows={5} required value={draft.instruction_markdown} onChange={(event) => setDraft({ ...draft, instruction_markdown: event.target.value })} /></label>
      <label className="field"><span>{t("schedule.agent")}</span><select value={draft.bot_id} onChange={(event) => setDraft({ ...draft, bot_id: event.target.value })}><option value="">{t("schedule.newAgent")}{selected ? ` · ${selected.split('/').at(-1)}` : ''}</option>{bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}</select></label>
      <div className="nx-schedule-fields"><label className="field"><span>{t("schedule.schedule")}</span><select value={['0 9 * * *','0 9 * * 1-5','0 9 * * 1'].includes(draft.cron_expression) ? draft.cron_expression : 'custom'} onChange={(event) => setDraft({ ...draft, cron_expression: event.target.value === 'custom' ? '* * * * *' : event.target.value })}><option value="0 9 * * *">{t("schedule.daily")}</option><option value="0 9 * * 1-5">{t("schedule.weekdays")}</option><option value="0 9 * * 1">{t("schedule.weekly")}</option><option value="custom">{t("schedule.custom")}</option></select></label><label className="field"><span>{t("schedule.timezone")}</span><input required value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })} /></label></div>
      {!['0 9 * * *','0 9 * * 1-5','0 9 * * 1'].includes(draft.cron_expression) && <label className="field"><span>{t("schedule.cron")}</span><input required value={draft.cron_expression} onChange={(event) => setDraft({ ...draft, cron_expression: event.target.value })} /></label>}
      <div className="dialog-actions"><button type="button" className="button button-quiet" disabled={busy} onClick={() => setEditing(false)}>{t("common.cancel")}</button><button type="submit" className="button button-primary" disabled={busy || !draft.name.trim() || !draft.instruction_markdown.trim() || (!draft.bot_id && !selected)}>{t(busy ? "schedule.saving" : "schedule.save")}</button></div>
    </form></div>}
    {history && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setHistory(null); }}><section className="modal-card nx-schedule-dialog" role="dialog" aria-modal="true" aria-label={t("schedule.history")}><header><div><h2>{history.name}</h2><p>{t("schedule.history")}</p></div><button type="button" className="ag-iconbtn" aria-label={t("common.close")} onClick={() => setHistory(null)}><Icon name="close" /></button></header>{runs === null ? <p className="ag-empty">{t("common.loading")}</p> : runs.length === 0 ? <p className="ag-empty">{t("schedule.noRuns")}</p> : <div className="nx-routine-history">{runs.map((item) => <article key={item.id}><header><time>{new Date(item.created_at).toLocaleString(dateLocale(locale))}</time><span>{statusLabel(t, item.status)}</span></header>{item.result && <MessageContent text={item.result} />}</article>)}</div>}</section></div>}
  </div>;
}
