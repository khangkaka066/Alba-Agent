import test from "node:test";
import assert from "node:assert/strict";
import { toYaml } from "../src/lib/workflow-format.mjs";

test("exports nested workflow objects and arrays as YAML scalars", () => {
  const document = toYaml({
    name: "Support: triage",
    nodes: [
      { id: "start", kind: "start", input_schema: { type: "object", properties: { request: { type: "string" } } } },
      { id: "review", kind: "approval", boundary_rules: ["email", "delete"] },
    ],
    enabled: true,
  });
  assert.match(document, /name: "Support: triage"/);
  assert.match(document, /- id: "start"/);
  assert.match(document, /input_schema:\n      type: "object"/);
  assert.match(document, /boundary_rules:\n      - "email"\n      - "delete"/);
  assert.match(document, /enabled: true/);
});

test("quotes workflow text so YAML punctuation remains data", () => {
  assert.equal(toYaml({ action: "email: delete # keep this literal" }), 'action: "email: delete # keep this literal"\n');
});
