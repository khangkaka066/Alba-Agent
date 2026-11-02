import test from "node:test";
import assert from "node:assert/strict";
import { diffLines, diffStatuses, fitnessDelta, lineageLabel, removedEdges, removedNodes, trendGeometry } from "../src/lib/team-evolution.mjs";

const diff = {
  added_nodes: ["audio_sync"], modified_nodes: ["story", "gate"], removed_nodes: ["summariser"],
  added_agents: { story: ["Audio & Subtitle Sync Specialist"] }, removed_agents: { summariser: ["Summariser"] },
};

test("colours each node by how the generation changed it, with additions winning over modifications", () => {
  assert.deepEqual(diffStatuses(diff), { story: "modified", gate: "modified", audio_sync: "added", summariser: "removed" });
  assert.deepEqual(diffStatuses(undefined), {});
  assert.deepEqual(diffStatuses({ added_nodes: ["x"], modified_nodes: ["x"] }), { x: "added" });
});

test("proposal lines name the agents that were added or pruned", () => {
  const lines = diffLines(diff).map((line) => line.text);
  assert.ok(lines.includes("+ Added Audio & Subtitle Sync Specialist in story"));
  assert.ok(lines.includes("- Pruned Summariser from summariser"));
  assert.ok(lines.includes("~ Changed node story"));
  assert.equal(diffLines(diff).find((line) => line.text.startsWith("- Pruned node"))?.tone, "removed");
});

test("pruned nodes and their edges are recovered from the parent generation", () => {
  const parent = { nodes: [{ id: "a" }, { id: "summariser" }], edges: [{ source: "a", target: "summariser" }, { source: "a", target: "b" }] };
  assert.deepEqual(removedNodes(parent, diff).map((node) => node.id), ["summariser"]);
  assert.deepEqual(removedEdges(parent, diff), [{ source: "a", target: "summariser" }]);
  assert.deepEqual(removedNodes({}, diff), []);
});

test("trendline places versions left to right and higher fitness higher up", () => {
  const { points, path } = trendGeometry([{ version: 1, fitness: 0.5 }, { version: 2, fitness: 0.9 }, { version: 3, fitness: 0.2 }, { version: 4, fitness: null }], 200, 100);
  assert.equal(points.length, 3);
  assert.ok(points[0].x < points[1].x && points[1].x < points[2].x);
  assert.ok(points[1].y < points[0].y && points[2].y > points[0].y);
  assert.match(path, /^M[\d.]+ [\d.]+ L/);
  assert.equal(trendGeometry([], 200, 100).path, "");
  assert.equal(trendGeometry([{ version: 1, fitness: 0.7 }], 200, 100).points[0].x, 100);
});

test("fitness deltas and lineage labels", () => {
  assert.ok(Math.abs(fitnessDelta({ fitness: 0.8 }, { fitness: 0.7 }) - 0.1) < 1e-9);
  assert.equal(fitnessDelta({ fitness: null }, { fitness: 0.7 }), null);
  assert.equal(lineageLabel([{ version: 1, status: "superseded" }, { version: 2, status: "rejected" }, { version: 3, status: "active" }]), "v1 → v3");
});
