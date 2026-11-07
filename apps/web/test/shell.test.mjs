import test from "node:test";
import assert from "node:assert/strict";
import { INITIAL_DOCK, PROJECTS_KEY, conversationTitle, dockAfter, groupConversations, loadProjects, normalizeUrl, rememberProject, reviewTotals } from "../src/lib/shell.mjs";

const memory = (initial = {}) => { const data = { ...initial }; return { getItem: (key) => data[key] ?? null, setItem: (key, value) => { data[key] = value; }, data }; };
const task = (id) => ({ run: { id }, name: id });

test("conversations group under the folder they were started in; the rest stay loose, newest first", () => {
  const groups = groupConversations([task("a"), task("b"), task("c"), task("d")], { a: "NexusAgent", c: "Lab_AI", d: "NexusAgent" });
  assert.deepEqual(groups.projects.map((project) => [project.name, project.tasks.map((item) => item.run.id)]), [["NexusAgent", ["a", "d"]], ["Lab_AI", ["c"]]]);
  assert.deepEqual(groups.loose.map((item) => item.run.id), ["b"]);
});

test("remembered projects survive a reload and ignore a damaged entry", () => {
  const storage = memory();
  rememberProject(storage, "run-1", "NexusAgent");
  assert.deepEqual(loadProjects(storage), { "run-1": "NexusAgent" });
  assert.deepEqual(loadProjects(memory({ [PROJECTS_KEY]: "{not json" })), {});
  assert.deepEqual(loadProjects(memory({ [PROJECTS_KEY]: JSON.stringify({ a: "x", b: 3, c: "" }) })), { a: "x" });
  rememberProject(storage, "", "x"); rememberProject(storage, "run-2", "");
  assert.deepEqual(Object.keys(loadProjects(storage)), ["run-1"]);
});

test("the remembered list is capped", () => {
  const storage = memory();
  for (let index = 0; index < 520; index += 1) rememberProject(storage, `run-${index}`, "P");
  const kept = loadProjects(storage);
  assert.equal(Object.keys(kept).length, 500);
  assert.ok(kept["run-519"] && !kept["run-0"]);
});

test("the dock opens on the tab asked for, toggles closed, and expands only while open", () => {
  let state = dockAfter(INITIAL_DOCK, { type: "show", tab: "terminal" });
  assert.deepEqual(state, { open: true, tab: "terminal", expanded: false });
  assert.equal(dockAfter(state, { type: "show", tab: "terminal" }).open, true, "showing the open tab does not close it");
  state = dockAfter(state, { type: "expand" });
  assert.equal(state.expanded, true);
  state = dockAfter(state, { type: "toggle" });
  assert.deepEqual(state, { open: false, tab: "terminal", expanded: false });
  assert.deepEqual(dockAfter(INITIAL_DOCK, { type: "show", tab: "nope" }), INITIAL_DOCK);
});

test("the address bar opens web pages only, and never turns words into a search", () => {
  assert.equal(normalizeUrl("example.com"), "https://example.com/");
  assert.equal(normalizeUrl("https://example.com/a?b=1"), "https://example.com/a?b=1");
  assert.equal(normalizeUrl("localhost:3000"), "http://localhost:3000/");
  assert.equal(normalizeUrl("127.0.0.1:8000/docs"), "http://127.0.0.1:8000/docs");
  for (const bad of ["", "  ", "javascript:alert(1)", "file:///etc/passwd", "data:text/html,hi", "hello world", "hello", "ftp://example.com"]) assert.equal(normalizeUrl(bad), null, bad);
});

test("review totals add up and an empty review is zero", () => {
  assert.deepEqual(reviewTotals([{ added: 5, removed: 1 }, { added: 2, removed: 0 }]), { added: 7, removed: 1 });
  assert.deepEqual(reviewTotals([]), { added: 0, removed: 0 });
});

test("a conversation title is one short line and never empty", () => {
  assert.equal(conversationTitle("  First line\nsecond", "Task"), "First line");
  assert.equal(conversationTitle("", "Task"), "Task");
  assert.equal(conversationTitle(undefined, "Task"), "Task");
  assert.equal(conversationTitle("x".repeat(200), "Task").length, 80);
});
