import assert from "node:assert/strict";
import test from "node:test";
import { MODEL_STORAGE_KEY, effortChoices, groupModels, loadModel, modelChoices, modelLabel, parseModelId, preferredModelVariant, resolveSelection, saveModel } from "../src/lib/models.mjs";

const models = [
  { id: "openai/gpt-4.1-mini", model: "gpt-4.1-mini", provider: "openai", group: "Server key", source: "platform", local: false },
  { id: "openai/gpt-4o", model: "gpt-4o", provider: "openai", group: "Server key", source: "platform", local: false },
  { id: "ollama/llama3.1:8b", model: "llama3.1:8b", provider: "ollama", group: "Ollama", source: "workspace", local: true },
  { id: "openrouter/openai/gpt-4.1-mini", model: "openai/gpt-4.1-mini", provider: "openrouter", group: "OpenRouter", source: "workspace", local: false },
];

const accountVariants = ["high", "medium", "low"].map((level) => ({
  id: `gemini/nexus-account-gemini:gemini-flash-${level}`, model: `Gemini Flash (${level[0].toUpperCase()}${level.slice(1)})`,
  provider: "gemini", group: "Google account", source: "workspace", local: false,
}));

test("model rows collapse efforts while effort selection retains the real dispatch id", () => {
  const low = accountVariants[2].id;
  const choices = modelChoices([...models, ...accountVariants], low);
  assert.equal(choices.length, models.length + 1);
  assert.equal(choices.at(-1).model, "Gemini Flash");
  assert.equal(choices.at(-1).id, low);
  assert.deepEqual(effortChoices(accountVariants, low).map((item) => item.value), ["low", "medium", "high"]);
  const data = new Map();
  const storage = {getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value)};
  saveModel(storage, effortChoices(accountVariants, low)[1].id);
  const restored = resolveSelection(accountVariants,loadModel(storage),accountVariants[0].id);
  assert.equal(restored, accountVariants[1].id);
  assert.equal(modelChoices(accountVariants,restored)[0].model,"Gemini Flash");
});

test("switching models preserves a supported effort without inventing provider options", () => {
  const pro = accountVariants.map((item)=>({...item,id:item.id.replace("flash","pro"),model:item.model.replace("Flash","Pro")}));
  assert.equal(preferredModelVariant([...accountVariants,...pro],pro[0].id,accountVariants[2].id),pro[2].id);
  assert.deepEqual(effortChoices(models,models[0].id),[]);
  assert.equal(preferredModelVariant([...models,...accountVariants],models[0].id,accountVariants[2].id),models[0].id);
  const plain = [{...models[0],id:"openai/gpt-high",model:"GPT (High)"}];
  assert.equal(modelChoices(plain,plain[0].id)[0].model,"GPT (High)");
  assert.deepEqual(effortChoices(plain,plain[0].id),[]);
});

test("Codex model and effort variants remain a single model with an independent effort selector", () => {
  const available = ["low","high","xhigh","ultra"].map(level=>({...models[0],id:`openai/nexus-account-codex:gpt-sol@${level}`,model:`GPT Sol (${level[0].toUpperCase()}${level.slice(1)})`}));
  assert.equal(modelChoices(available,available[1].id).length,1);
  assert.equal(modelChoices(available,available[1].id)[0].model,"GPT Sol");
  assert.deepEqual(effortChoices(available,available[1].id).map(item=>item.value),["low","high","xhigh","ultra"]);
  assert.equal(effortChoices(available,available[1].id)[2].id,"openai/nexus-account-codex:gpt-sol@xhigh");
});

test("labels drop the provider but keep model names that contain a slash", () => {
  assert.equal(modelLabel("openai/gpt-4o"), "gpt-4o");
  assert.equal(modelLabel("openrouter/openai/gpt-4.1-mini"), "openai/gpt-4.1-mini");
  assert.equal(modelLabel("claude"), "claude");
  assert.equal(modelLabel(null), "");
  assert.equal(modelLabel("gemini/nexus-account-gemini:gemini-3.8-flash-low"), "gemini-3.8-flash-low");
});

test("a legacy account selection migrates to its own concrete model without changing accounts", () => {
  const available = [...models, {id:"gemini/nexus-account-gemini:gemini-3.8-flash-high",provider:"gemini",model:"Gemini 3.8 Flash (High)"}];
  assert.equal(resolveSelection(available,"gemini/nexus-account-gemini:default",models[0].id,["gemini"]),available.at(-1).id);
  assert.equal(resolveSelection(available,"gemini/nexus-account-gemini:gemini-3.8-flash-high",models[0].id,["gemini"]),available.at(-1).id);
});

test("a removed Copilot selection cannot survive through another OpenAI connection", () => {
  assert.equal(resolveSelection(models,"openai/nexus-account-copilot:default",models[0].id,["openai"]),models[0].id);
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

import { loadRecent, pickerView, rememberRecent } from "../src/lib/models.mjs";

const sample = [
  { id: "openai/gpt-5.4", provider: "openai", model: "gpt-5.4", group: "OpenAI", local: false },
  { id: "openai/gpt-5-mini", provider: "openai", model: "gpt-5-mini", group: "OpenAI", local: false },
  { id: "deepseek/deepseek-chat", provider: "deepseek", model: "deepseek-chat", group: "DeepSeek", local: false },
];

test("recent models keep the newest first, without repeats, and are capped", () => {
  const data = {};
  const storage = { getItem: (key) => data[key] ?? null, setItem: (key, value) => { data[key] = value; } };
  for (const id of ["a/1", "b/2", "c/3", "a/1", "d/4"]) rememberRecent(storage, id);
  assert.deepEqual(loadRecent(storage), ["d/4", "a/1", "c/3"]);
  assert.deepEqual(loadRecent({ getItem: () => "not json" }), []);
});

test("pickerView shows recent models that still run plus one row per provider; a search flattens to matches", () => {
  const view = pickerView(sample, ["deepseek/deepseek-chat", "gone/model"]);
  assert.deepEqual(view.recent.map((item) => item.id), ["deepseek/deepseek-chat"]);
  assert.deepEqual(view.providers.map((group) => [group.name, group.models.length]), [["OpenAI", 2], ["DeepSeek", 1]]);
  const found = pickerView(sample, ["deepseek/deepseek-chat"], "MINI");
  assert.deepEqual(found.matches.map((item) => item.id), ["openai/gpt-5-mini"]);
  assert.deepEqual(found.providers, []);
});
