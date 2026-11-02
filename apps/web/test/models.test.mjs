import assert from "node:assert/strict";
import test from "node:test";
import { MODEL_STORAGE_KEY, groupModels, loadModel, modelLabel, parseModelId, resolveSelection, saveModel } from "../src/lib/models.mjs";

const models = [
  { id: "openai/gpt-4.1-mini", model: "gpt-4.1-mini", provider: "openai", group: "Server key", source: "platform", local: false },
  { id: "openai/gpt-4o", model: "gpt-4o", provider: "openai", group: "Server key", source: "platform", local: false },
  { id: "ollama/llama3.1:8b", model: "llama3.1:8b", provider: "ollama", group: "Ollama", source: "workspace", local: true },
  { id: "openrouter/openai/gpt-4.1-mini", model: "openai/gpt-4.1-mini", provider: "openrouter", group: "OpenRouter", source: "workspace", local: false },
];

test("labels drop the provider but keep model names that contain a slash", () => {
  assert.equal(modelLabel("openai/gpt-4o"), "gpt-4o");
  assert.equal(modelLabel("openrouter/openai/gpt-4.1-mini"), "openai/gpt-4.1-mini");
  assert.equal(modelLabel("claude"), "claude");
  assert.equal(modelLabel(null), "");
});

test("the remembered model wins while it exists, then the server default, then the first model", () => {
  assert.equal(resolveSelection(models, "openai/gpt-4o", "openai/gpt-4.1-mini"), "openai/gpt-4o");
  assert.equal(resolveSelection(models, "gone/model", "ollama/llama3.1:8b"), "ollama/llama3.1:8b");
  assert.equal(resolveSelection(models, null, "gone/model"), "openai/gpt-4.1-mini");
  assert.equal(resolveSelection([], "openai/gpt-4o", "openai/gpt-4.1-mini"), null);
  assert.equal(resolveSelection(undefined, null, null), null);
});

test("groups keep server order inside a group and put models on this machine first", () => {
  const groups = groupModels(models);
  assert.deepEqual(groups.map((group) => group.name), ["Ollama", "Server key", "OpenRouter"]);
  assert.deepEqual(groups[1].models.map((item) => item.model), ["gpt-4.1-mini", "gpt-4o"]);
  assert.deepEqual(groupModels(null), []);
});

test("the choice is stored under one key and a blocked store is survivable", () => {
  const data = {};
  const storage = { getItem: (key) => data[key] ?? null, setItem: (key, value) => { data[key] = value; }, removeItem: (key) => { delete data[key]; } };
  saveModel(storage, "openai/gpt-4o");
  assert.deepEqual(data, { [MODEL_STORAGE_KEY]: "openai/gpt-4o" });
  assert.equal(loadModel(storage), "openai/gpt-4o");
  saveModel(storage, null);
  assert.equal(loadModel(storage), null);
  const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } };
  assert.equal(loadModel(blocked), null);
  assert.doesNotThrow(() => saveModel(blocked, "x"));
});

test("a typed model id needs a provider and a model, and nothing else", () => {
  assert.deepEqual(parseModelId(" openai/gpt-4.1 "), { provider: "openai", model: "gpt-4.1", id: "openai/gpt-4.1" });
  assert.deepEqual(parseModelId("openrouter/meta-llama/llama-3.3-70b:free"), { provider: "openrouter", model: "meta-llama/llama-3.3-70b:free", id: "openrouter/meta-llama/llama-3.3-70b:free" });
  for (const bad of ["gpt-4.1", "/gpt", "openai/", "OpenAI/gpt", "open ai/gpt", "openai/gpt 4", "", null, 42, "openai/" + "x".repeat(200)]) assert.equal(parseModelId(bad), null, String(bad));
});

test("a typed model is kept only while its provider is connected", () => {
  assert.equal(resolveSelection(models, "openai/gpt-4.1", "openai/gpt-4.1-mini", ["openai"]), "openai/gpt-4.1");
  assert.equal(resolveSelection(models, "openai/gpt-4.1", "openai/gpt-4.1-mini", []), "openai/gpt-4.1-mini");
  assert.equal(resolveSelection(models, "anthropic/claude-opus-4-6", "openai/gpt-4.1-mini", ["openai"]), "openai/gpt-4.1-mini");
  assert.equal(resolveSelection(models, "not a model", null, ["openai"]), "openai/gpt-4.1-mini");
});
