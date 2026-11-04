import assert from "node:assert/strict";
import test from "node:test";
import { failureDetails, failureFacts, orderTasks, statusTone } from "../src/lib/history.mjs";

test("each run status maps to one indicator colour", () => {
  assert.deepEqual(["completed", "failed", "cancelled", "running", "queued", "paused", "?"].map(statusTone), ["ok", "bad", "bad", "busy", "busy", "wait", "idle"]);
});

test("unfinished tasks come first, then the newest, and the open task is never dropped", () => {
  const runs = [
    { id: "old-done", status: "completed", created_at: "2026-11-01T10:00:00Z" },
    { id: "new-done", status: "completed", created_at: "2026-11-02T10:00:00Z" },
    { id: "working", status: "running", created_at: "2026-10-30T10:00:00Z" },
    { id: "waiting", status: "paused", created_at: "2026-10-29T10:00:00Z" },
  ];
  assert.deepEqual(orderTasks(runs, null).map((run) => run.id), ["working", "waiting", "new-done", "old-done"]);
  assert.deepEqual(orderTasks(runs, "old-done", 2).map((run) => run.id), ["working", "old-done"]);
  assert.deepEqual(orderTasks(null, null), []);
});

test("a failure reads as where it stopped, which agent when known, and what went wrong", () => {
  const failure = { failed_node_id: "art", failed_node_label: "Dept C", failed_agent_name: null, error_type: "ValueError", error_message: "No media", traceback_summary: "a.py:1 in run" };
  assert.deepEqual(failureFacts(failure), [{ key: "where", value: "Dept C" }, { key: "message", value: "No media" }]);
  assert.deepEqual(failureFacts({ ...failure, failed_agent_name: "Colourist" }).map((fact) => fact.key), ["where", "agent", "message"]);
  assert.equal(failureDetails(failure), "ValueError\na.py:1 in run");
  for (const none of [null, undefined, "x", {}]) { assert.deepEqual(failureFacts(none), []); assert.equal(failureDetails(none), ""); }
});

import { ageLabel, filterTasks } from "../src/lib/history.mjs";

test("ageLabel is compact and steps through minutes, hours, days and weeks", () => {
  const now = Date.parse("2026-11-04T12:00:00Z");
  const ago = (ms) => new Date(now - ms).toISOString();
  assert.equal(ageLabel(ago(10_000), now), "now");
  assert.equal(ageLabel(ago(5 * 60_000), now), "5m");
  assert.equal(ageLabel(ago(3 * 3_600_000), now), "3h");
  assert.equal(ageLabel(ago(2 * 86_400_000), now), "2d");
  assert.equal(ageLabel(ago(15 * 86_400_000), now), "2w");
  assert.equal(ageLabel("not a date", now), "");
});

test("filterTasks keeps tasks whose name contains the query, ignoring case", () => {
  const tasks = [{ name: "Fix parser" }, { name: "Write docs" }];
  assert.deepEqual(filterTasks(tasks, "DOCS"), [{ name: "Write docs" }]);
  assert.deepEqual(filterTasks(tasks, "  "), tasks);
});
