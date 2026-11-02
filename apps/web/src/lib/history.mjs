// Task history helpers: how a run's status looks in the sidebar, and what a failure says in plain words.

/** Colour group for a run status: done, failed, working, waiting for the person, or anything else. */
export function statusTone(status) {
  if (status === "completed") return "ok";
  if (status === "failed" || status === "cancelled") return "bad";
  if (status === "running" || status === "queued") return "busy";
  if (status === "paused") return "wait";
  return "idle";
}

/** Tasks in the order shown: unfinished work first, then newest first. A task that is open is always included. */
export function orderTasks(runs, currentRunId, limit = 30) {
  const rows = Array.isArray(runs) ? [...runs] : [];
  const busy = (run) => (statusTone(run.status) === "busy" || statusTone(run.status) === "wait" ? 0 : 1);
  rows.sort((a, b) => busy(a) - busy(b) || String(b.created_at).localeCompare(String(a.created_at)));
  const kept = rows.slice(0, limit);
  const open = rows.find((run) => run.id === currentRunId);
  return open && !kept.includes(open) ? [...kept.slice(0, limit - 1), open] : kept;
}

/** The facts of a failure worth showing, in order, skipping the ones that are not known. */
export function failureFacts(failure) {
  if (!failure || typeof failure !== "object") return [];
  const facts = [];
  if (failure.failed_node_label || failure.failed_node_id) facts.push({ key: "where", value: String(failure.failed_node_label ?? failure.failed_node_id) });
  if (failure.failed_agent_name) facts.push({ key: "agent", value: String(failure.failed_agent_name) });
  if (failure.error_message) facts.push({ key: "message", value: String(failure.error_message) });
  return facts;
}

/** Technical details kept behind a "details" toggle. */
export function failureDetails(failure) {
  if (!failure || typeof failure !== "object") return "";
  return [failure.error_type, failure.traceback_summary].filter((part) => typeof part === "string" && part).join("\n");
}
