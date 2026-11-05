"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { PromptBox } from "./prompt-box";
import { SlashMenu } from "./composer";
import { getDesktop } from "@/lib/desktop";
import { dateLocale, statusLabel } from "@/lib/i18n.mjs";
import { apiRequest } from "@/lib/api";
import { useWorkspace, type Rigor } from "./workspace-context";

const SCALES: Rigor[] = ["auto", "minimal", "standard", "full_studio"];
const STARTERS = ["home.starter.museum", "home.starter.excel", "home.starter.webapp"];
type RecentRun = { id: string; workflow_id: string; status: string; created_at: string };
const when = (iso: string, locale: string) => new Date(iso).toLocaleString(dateLocale(locale), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** State A: nothing is running, so the screen is one centred question and a few ways to start. */
export function StudioHome({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { t, locale } = useLocale();
  const workspace = useWorkspace();
  const [text, setText] = useState("");
  const [slash, setSlash] = useState(false);
  const [rigor, setRigor] = useState<Rigor>("auto");
  const [recent, setRecent] = useState<Array<RecentRun & { name: string }>>([]);
  const desktop = getDesktop();
  const { token } = workspace;

  useEffect(() => {
    if (!token) return;
    let stopped = false;
    void Promise.all([apiRequest<RecentRun[]>("/api/v1/runs", token), apiRequest<Array<{ id: string; name: string }>>("/api/v1/workflows", token)])
      .then(([runs, workflows]) => {
        if (stopped) return;
        const names = Object.fromEntries(workflows.map((item) => [item.id, item.name]));
        setRecent(runs.slice(0, 6).map((run) => ({ ...run, name: names[run.workflow_id] ?? "" })));
      }).catch(() => undefined);
    return () => { stopped = true; };
  }, [token]);

  const submit = (value: string) => {
    const prompt = value.trim();
    if (!prompt || workspace.busy || !token) return;
    setText("");
    void workspace.startTask(prompt, rigor);
  };

  return <div className="studio-home">
    <div className="studio-home__inner">
      <h1>{t("home.title")}</h1>
      <form className="ag-composer" onSubmit={(event) => { event.preventDefault(); submit(text); }}>
        {slash && <SlashMenu onClose={() => setSlash(false)} />}
        <PromptBox value={text} onChange={setText} onSubmit={() => submit(text)} onSlash={() => setSlash(true)} onOpenSettings={onOpenSettings} autoFocus rows={3}
          label={t("home.promptLabel")} placeholder={t(token ? "prompt.placeholder" : "home.starting")} busy={workspace.busy} canSend={Boolean(text.trim() && token)}>
          {desktop && <button type="button" className="ag-chip" onClick={() => void workspace.openFolder()} title={workspace.folder?.root}><Icon name="folder" size={14} />
            {workspace.folder ? t("home.folder", { name: workspace.folder.name, count: workspace.folder.files.length }) : t("home.openFolder")}</button>}
          <label className="scale-select"><span>{t("home.scale")}</span>
            <select aria-label={t("home.scale")} value={rigor} onChange={(event) => setRigor(event.target.value as Rigor)} disabled={workspace.busy}>
              {SCALES.map((option) => <option key={option} value={option}>{t(`home.scale.${option}`)}</option>)}</select></label>
        </PromptBox>
      </form>
      <div className="starter-chips" aria-label={t("home.hints")}>{STARTERS.map((key) => <button key={key} className="chip chip--starter" disabled={workspace.busy || !token} onClick={() => submit(t(key))}>{t(key)}</button>)}</div>
      {recent.length > 0 && <section className="recent-tasks" aria-label={t("home.recentLabel")}><h2>{t("home.recent")}</h2>
        <ul>{recent.map((run) => <li key={run.id}><button onClick={() => workspace.openRun(run.workflow_id, run.id, run.name || t("common.task"))}>
          <span className={`run-dot run-dot--${run.status === "queued" ? "idle" : run.status}`} /><span className="recent-tasks__name">{run.name || t("common.task")}</span>
          <span className="recent-tasks__meta">{statusLabel(t, run.status)} · {when(run.created_at, locale)}</span></button></li>)}</ul></section>}
    </div>
  </div>;
}
