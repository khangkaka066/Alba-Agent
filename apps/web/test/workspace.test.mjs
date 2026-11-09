import test from "node:test";
import assert from "node:assert/strict";
import { buildTree, classifyArtifact, diffStats, fileStatuses, flattenWorkspaceFiles, initialRunState, isFinished, lineDiff, liveActivity, reduceRunEvent, runAnswer, splitRows, stepLabel, teamSummary } from "../src/lib/workspace.mjs";

test("artifacts open in the right viewer", () => {
  assert.deepEqual(classifyArtifact("tour.mp4"), { kind: "video", text: false });
  assert.deepEqual(classifyArtifact("chart.PNG"), { kind: "image", text: false });
  assert.deepEqual(classifyArtifact("auth/service.py"), { kind: "code", text: true });
  assert.deepEqual(classifyArtifact("report.md"), { kind: "document", text: true });
  assert.deepEqual(classifyArtifact("blob.bin", "text/plain"), { kind: "document", text: true });
  assert.equal(classifyArtifact("paper.pdf").kind, "pdf");
  assert.equal(classifyArtifact("noext").kind, "other");
});

test("the tree puts folders first and carries each file status", () => {
  const tree = buildTree(["b.md", "src/z.py", "src/a.py", "README.md"], { "src/a.py": "added", "b.md": "modified" });
  assert.deepEqual(tree.map((n) => n.name), ["src", "b.md", "README.md"]);
  assert.deepEqual(tree[0].children.map((n) => n.name), ["a.py", "z.py"]);
  assert.equal(tree[0].children[0].status, "added");
  assert.equal(tree[1].status, "modified");
  assert.deepEqual(fileStatuses({ a: 1, b: 2, c: 3 }, { a: 1, b: 9 }), { b: "modified", c: "added" });
});

test("line diff marks only what changed and numbers both sides", () => {
  const ops = lineDiff("a\nb\nc\nd", "a\nB\nc\nd\ne");
  assert.deepEqual(ops.map((o) => o.type), ["same", "del", "add", "same", "same", "add"]);
  assert.deepEqual(diffStats(ops), { added: 2, removed: 1 });
  assert.deepEqual([ops[1].oldNo, ops[1].newNo, ops[2].oldNo, ops[2].newNo], [2, null, null, 2]);
  assert.deepEqual(lineDiff("", "x\ny").map((o) => o.type), ["add", "add"]);
  assert.deepEqual(lineDiff("same", "same").map((o) => o.type), ["same"]);
  assert.equal(diffStats(lineDiff("x\ny", "")).removed, 2);
});

test("split rows pair a removal with its replacement", () => {
  const rows = splitRows(lineDiff("a\nb\nc", "a\nB1\nB2\nc"));
  assert.equal(rows.length, 4);
  assert.equal(rows[1].left.text, "b"); assert.equal(rows[1].right.text, "B1");
  assert.equal(rows[2].left, null); assert.equal(rows[2].right.text, "B2");
});

test("the team pill counts agents across departments and sandboxes", () => {
  const spec = { modes: { rigor: "full_studio" }, nodes: [
    { id: "start", kind: "start" },
    { id: "dir", kind: "crew", agents: [{ tier: "director" }, { tier: "lead" }, { tier: "specialist" }] },
    { id: "box", kind: "sandbox" },
    { id: "gate", kind: "approval" },
  ] };
  const team = teamSummary(spec);
  assert.deepEqual([team.agents, team.crews, team.sandboxes, team.steps, team.rigor], [5, 1, 1, 3, "full_studio"]);
  assert.equal(team.label, "Director → Department crews → Sandbox");
  assert.deepEqual(teamSummary(null), { agents: 0, crews: 0, sandboxes: 0, steps: 0, tiers: {}, label: "Workflow", rigor: null });
});

test("run events fold into progress, terminal output and approvals", () => {
  let s = initialRunState();
  const ev = (type, payload = {}, node = null) => ({ id: `${type}-${Math.random()}`, run_id: "r1", type, node_id: node, occurred_at: "", payload });
  s = reduceRunEvent(s, ev("FLOW_STATE_CHANGED", { status: "running", node_id: "crew" }));
  assert.deepEqual([s.status, s.active], ["running", ["crew"]]);
  s = reduceRunEvent(s, ev("CREW_AGENT_THOUGHT", { content: "Reading the sales file" }, "crew"));
  assert.match(liveActivity(s), /Reading the sales file/);
  s = reduceRunEvent(s, ev("SANDBOX_TERMINAL_OUTPUT", { stream: "stdout", content: "ok" }));
  assert.equal(s.terminal[0].text, "ok");
  s = reduceRunEvent(s, ev("FLOW_STATE_CHANGED", { status: "completed", node_id: "crew" }));
  assert.deepEqual([s.completed, s.active, stepLabel(s, 4)], [["crew"], [], "Bước 2/4"]);
  s = reduceRunEvent(s, ev("APPROVAL_REQUIRED", { approval_id: "a1", action: "Send report" }, "gate"));
  assert.deepEqual([s.status, s.approvals.length, liveActivity(s)], ["paused", 1, "Đang chờ bạn duyệt"]);
  s = reduceRunEvent(s, ev("APPROVAL_REQUIRED", { approval_id: "a1", action: "Send report" }, "gate"));
  assert.equal(s.approvals.length, 1, "a repeated approval event is not added twice");
  s = reduceRunEvent(s, ev("APPROVAL_RESOLVED", { approval_id: "a1", decision: "allow_once" }));
  assert.deepEqual([s.status, s.approvals.length], ["running", 0]);
  s = reduceRunEvent(s, ev("RUN_COMPLETED"));
  assert.equal(isFinished(s.status), true);
  assert.equal(reduceRunEvent(initialRunState(), ev("RUN_FAILED", { message: "boom" })).error, "boom");
  assert.equal(reduceRunEvent(initialRunState(), ev("SANDBOX_SCREEN_FRAME", { mime_type: "image/png", data_base64: "AAA" })).frame, "data:image/png;base64,AAA");
});

test("a mounted folder is flattened for the sandbox with a path manifest", () => {
  const out = flattenWorkspaceFiles([
    { path: "src/auth/service.py", content: "print('a')" }, { path: "tests/service.py", content: "print('t')" },
    { path: ".env", content: "SECRET=1" }, { path: "big.txt", content: "x".repeat(50) },
  ], 60);
  assert.deepEqual(Object.keys(out.files).sort(), ["service.py", "service_2.py", "workspace_manifest.json"], "dotfiles and over-budget files are left out");
  assert.deepEqual([out.map["service.py"], out.map["service_2.py"]], ["src/auth/service.py", "tests/service.py"]);
  const roomy = flattenWorkspaceFiles([{ path: "a/x.py", content: "1" }]);
  assert.equal(JSON.parse(roomy.files["workspace_manifest.json"]).files["x.py"], "a/x.py");
});

test("activity uses real events and updates a tool call instead of duplicating its start and finish", () => {
  let state = initialRunState();
  const event = (id, type, payload) => ({ id, type, node_id: "build", occurred_at: "2026-11-08T01:00:00Z", payload });
  state = reduceRunEvent(state, event("note", "CREW_AGENT_THOUGHT", { content: "I will inspect the file." }));
  state = reduceRunEvent(state, event("start", "TOOL_INVOKED", { call_id: "call-1", tool: "Read file", detail: "demo/index.html", phase: "started" }));
  state = reduceRunEvent(state, event("done", "TOOL_INVOKED", { call_id: "call-1", tool: "Read file", detail: "demo/index.html", phase: "completed" }));
  assert.equal(state.activity.length, 2);
  assert.equal(state.activity[0].text, "I will inspect the file.");
  assert.equal(state.activity[1].phase, "completed");
  assert.equal(state.activity[1].detail, "demo/index.html");
  assert.equal(initialRunState().activity.length, 0);
});


test("completed results use the actual answer, never intermediate thoughts or trigger input", () => {
  assert.equal(runAnswer({ start: { request: "hi" }, greeting: { response: "Chào bạn!" } }), "Chào bạn!");
  assert.equal(runAnswer({ step: { thought: "I need to greet the user", analysis: "internal plan" } }), "");
  assert.equal(runAnswer({ a: { summary: "Working" }, b: { result: { answer: "385" } } }), "385");
  assert.equal(runAnswer(null), "");
});

test('stopping waits for acknowledgement and cannot be undone by an in-flight completion event', () => {
  const event = (status) => ({ id: status, type: 'FLOW_STATE_CHANGED', payload: { status }, run_id: 'r1' });
  let state = { ...initialRunState(), status: 'running', active: ['worker'], approvals: [{ approval_id: 'a' }] };
  state = reduceRunEvent(state, event('cancelling'));
  assert.equal(isFinished(state.status), false);
  state = reduceRunEvent(state, { id: 'done', type: 'RUN_COMPLETED', payload: {}, run_id: 'r1' });
  assert.equal(state.status, 'cancelling');
  state = reduceRunEvent(state, event('cancelled'));
  assert.equal(isFinished(state.status), true);
  assert.deepEqual([state.active, state.approvals], [[], []]);
  assert.equal(reduceRunEvent(state, event('running')).status, 'cancelled');
});
