import test from "node:test";
import assert from "node:assert/strict";
import { OPERATOR_CODES, RIGOR_OPTIONS, groupAgentsByTier, hasTiers, parseJsonList, routesToText } from "../src/lib/studio-spec.mjs";

const agents = [
  { id: "d_lead", role: "Design Lead", tier: "lead", model: "m", skill_ids: [], tool_ids: [] },
  { id: "d_sys", role: "Systems Designer", tier: "specialist", model: "m", skill_ids: ["s1"], tool_ids: ["report_exporter"] },
  { id: "d_ux", role: "UX Designer", tier: "specialist", model: "m", skill_ids: [], tool_ids: [] },
  { id: "plain", role: "Plain" },
];
const tasks = [
  { agent_id: "d_sys", expected_artifact_paths: ["design/systems.md", "design/systems.md"] },
  { agent_id: "d_ux", expected_artifact_paths: ["design/ux.md"] },
];

test("groups agents by tier and attaches each specialist's artifact paths", () => {
  const groups = groupAgentsByTier(agents, tasks);
  assert.deepEqual(groups.lead.map((agent) => agent.role), ["Design Lead"]);
  assert.deepEqual(groups.specialist.map((agent) => agent.id), ["d_sys", "d_ux"]);
  assert.deepEqual(groups.specialist[0].paths, ["design/systems.md"]);
  assert.deepEqual(groups.specialist[0].tools, ["report_exporter"]);
  assert.equal(groups.untiered.length, 1);
  assert.equal(hasTiers(groups), true);
});

test("a legacy crew without tiers is not shown as a studio", () => {
  assert.equal(hasTiers(groupAgentsByTier([{ id: "a", role: "A" }], [])), false);
  assert.equal(hasTiers(groupAgentsByTier(undefined, undefined)), false);
});

test("router rules survive a text round trip with their names", () => {
  const text = routesToText([
    { name: "pass", field_path: "quality_gate__gate.gate_passed", operator: "eq", value: true },
    { name: "rework_build", field_path: "quality_gate__gate.failing_department", operator: "eq", value: "build" },
    { name: "has_files", field_path: "build.files", operator: "exists" },
  ]);
  assert.equal(text, "quality_gate__gate.gate_passed == true → pass\nquality_gate__gate.failing_department == build → rework_build\nbuild.files exists → has_files");
  assert.equal(OPERATOR_CODES[">="], "gte");
});

test("rigor choices and path lists", () => {
  assert.deepEqual(RIGOR_OPTIONS.map((option) => option.value), ["auto", "minimal", "standard", "full_studio"]);
  assert.deepEqual(parseJsonList('["a.md","b/c.md",3]'), ["a.md", "b/c.md"]);
  assert.deepEqual(parseJsonList("not json"), []);
});
