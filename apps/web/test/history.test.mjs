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
