"use client";

import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { usePreferences } from "@/components/settings/preferences-provider";
import { useWorkspace } from "./workspace-context";

/** Only runtime events are shown: no generated waiting text or pretend reasoning. */
export function ActivityLog() {
  const { t } = useLocale();
  const { run } = useWorkspace();
  const { preferences } = usePreferences();
  const verbose = preferences.steps === "verbose";
  const rows = run.activity.slice(verbose ? -64 : -16);
  if (!rows.length) return null;
  return <ol className="ag-activity-log nx-tool-log" role="log" aria-label={t("activity.title")} aria-live="polite" aria-relevant="additions text">
    {rows.map((row) => <li key={row.id} className={row.phase === "failed" ? "has-error" : ""}>
      <details open={verbose}><summary><Icon name={row.type === "CREW_AGENT_THOUGHT" ? "chat" : row.phase === "completed" ? "check" : row.phase === "failed" ? "stop" : "terminal"} size={14} /><span>{row.type === "CREW_AGENT_THOUGHT" ? t("interface.agentUpdate") : row.tool || t("activity.code")}</span>{row.phase && <small>{t(`activity.${row.phase}`)}</small>}<Icon name="chevronRight" size={12} /></summary>{row.type === "CREW_AGENT_THOUGHT" ? <p>{row.text}</p> : <>{row.detail && <pre>{row.detail}</pre>}{row.output && <pre className="nx-tool-output">{row.output}</pre>}{!row.detail && !row.output && <p>{t("interface.noToolDetails")}</p>}</>}</details>
    </li>)}
  </ol>;
}
