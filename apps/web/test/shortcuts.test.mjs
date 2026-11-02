import test from "node:test";
import assert from "node:assert/strict";
import { ACTIONS, DEFAULT_BINDINGS, actionFor, comboFromEvent, findConflict, formatCombo, isValidCombo, loadBindings, overridesOf, resolveBindings, saveBindings } from "../src/lib/shortcuts.mjs";

const key = (k, mods = {}) => ({ key: k, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...mods });

test("events become the same combo on macOS (Cmd) and elsewhere (Ctrl)", () => {
  assert.equal(comboFromEvent(key("k", { metaKey: true })), "Mod+K");
  assert.equal(comboFromEvent(key("K", { ctrlKey: true })), "Mod+K");
  assert.equal(comboFromEvent(key("Enter", { ctrlKey: true, shiftKey: true })), "Mod+Shift+Enter");
  assert.equal(comboFromEvent(key(" ", { altKey: true })), "Alt+Space");
  assert.equal(comboFromEvent(key("Meta", { metaKey: true })), "");
});

test("a binding must not steal plain typing or the Escape that closes dialogs", () => {
  for (const combo of ["Mod+K", "Alt+J", "F5", "Mod+Shift+,"]) assert.equal(isValidCombo(combo), true, combo);
  for (const combo of ["K", "Shift+K", "Escape", "Mod+Escape", "Mod", "", "Enter"]) assert.equal(isValidCombo(combo), false, combo);
});

test("combos read naturally on each platform", () => {
  assert.equal(formatCombo("Mod+Shift+K", true), "⌘ ⇧ K");
  assert.equal(formatCombo("Mod+Enter", true), "⌘ ↵");
  assert.equal(formatCombo("Mod+Shift+K", false), "Ctrl+Shift+K");
});

test("saved overrides apply, while invalid or colliding ones fall back to the defaults", () => {
  assert.deepEqual(resolveBindings(null), DEFAULT_BINDINGS);
  assert.equal(resolveBindings({ palette: "Mod+P" }).palette, "Mod+P");
  assert.equal(resolveBindings({ palette: "K" }).palette, "Mod+K");
  const clash = resolveBindings({ palette: "Mod+1" });
  assert.equal(clash["nav-studio"], "Mod+1", "the action that owns a default keeps it over a colliding override");
  assert.equal(clash.palette, "Mod+K");
  assert.equal(new Set(Object.values(clash)).size, ACTIONS.length, "no two actions share a combo");
});

test("conflicts name the action that already owns the combo", () => {
  assert.equal(findConflict(DEFAULT_BINDINGS, "palette", "Mod+1"), "nav-studio");
  assert.equal(findConflict(DEFAULT_BINDINGS, "palette", "Mod+K"), null);
});

test("only changes are stored, and a bad store never breaks the app", () => {
  assert.deepEqual(overridesOf({ ...DEFAULT_BINDINGS, run: "Mod+R" }), { run: "Mod+R" });
  const memory = new Map();
  const storage = { getItem: (k) => memory.get(k) ?? null, setItem: (k, v) => memory.set(k, v) };
  saveBindings(storage, { ...DEFAULT_BINDINGS, run: "Mod+R" });
  assert.equal(loadBindings(storage).run, "Mod+R");
  assert.deepEqual(loadBindings({ getItem: () => "{broken" }), DEFAULT_BINDINGS);
  assert.deepEqual(loadBindings({ getItem: () => { throw new Error("blocked"); } }), DEFAULT_BINDINGS);
});

test("pressing a bound combo finds its action", () => {
  assert.equal(actionFor(DEFAULT_BINDINGS, key("2", { metaKey: true })), "nav-integrations");
  assert.equal(actionFor(DEFAULT_BINDINGS, key("x", { metaKey: true })), null);
  assert.equal(actionFor({ ...DEFAULT_BINDINGS, run: "Mod+R" }, key("r", { ctrlKey: true })), "run");
});
