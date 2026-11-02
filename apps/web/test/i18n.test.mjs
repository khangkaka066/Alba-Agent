import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { DEFAULT_LOCALE, LOCALE_STORAGE_KEY, createTranslator, dateLocale, loadLocale, resolveLocale, saveLocale, statusLabel } from "../src/lib/i18n.mjs";
import { MESSAGES } from "../src/lib/messages.mjs";
import { ACTIONS } from "../src/lib/shortcuts.mjs";
import { initialRunState, liveActivity, reduceRunEvent, stepLabel } from "../src/lib/workspace.mjs";

const placeholders = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();

test("Vietnamese and English define exactly the same keys with the same placeholders", () => {
  assert.deepEqual(Object.keys(MESSAGES.vi).sort(), Object.keys(MESSAGES.en).sort());
  for (const key of Object.keys(MESSAGES.vi)) assert.deepEqual(placeholders(MESSAGES.en[key]), placeholders(MESSAGES.vi[key]), key);
});

test("every translation is filled in and English is not a copy of the Vietnamese text", () => {
  for (const [key, text] of Object.entries(MESSAGES.en)) assert.ok(text.trim(), key);
  const same = Object.keys(MESSAGES.vi).filter((key) => MESSAGES.vi[key] === MESSAGES.en[key] && /[A-Za-zÀ-ỹ]{4,}/.test(MESSAGES.vi[key]));
  assert.deepEqual(same.filter((key) => !["settings.s2.title", "failure.agent"].includes(key)), []);
});

test("source code only asks for keys that exist", () => {
  const used = new Set();
  const walk = (dir) => { for (const name of readdirSync(dir)) { const path = join(dir, name); if (statSync(path).isDirectory()) walk(path); else if (/\.(tsx?|mjs)$/.test(name) && !name.endsWith(".d.mts")) {
    const source = readFileSync(path, "utf8");
    for (const match of source.matchAll(/\bt\(\s*"([\w.-]+)"/g)) used.add(match[1]);
    for (const match of source.matchAll(/\bt\(\s*`([\w.-]+)\.\$\{/g)) used.add(`${match[1]}.*`);
    for (const match of source.matchAll(/"((?:run|stage|chat|home|files|tools|hub|palette|shell|pill|common|page|settings|harness|terminal|workspace|architect|language)\.[\w.-]+)"/g)) used.add(match[1]);
  } } };
  walk(new URL("../src", import.meta.url).pathname);
  const missing = [...used].filter((key) => !key.endsWith(".*") && !(key in MESSAGES.vi));
  assert.deepEqual(missing, []);
  for (const prefix of [...used].filter((key) => key.endsWith(".*")).map((key) => key.slice(0, -2))) assert.ok(Object.keys(MESSAGES.vi).some((key) => key.startsWith(`${prefix}.`)), prefix);
});

test("placeholders are filled and a missing key falls back to English, then to the key", () => {
  const vi = createTranslator("vi"), en = createTranslator("en");
  assert.equal(vi("run.step", { current: 2, total: 4 }), "Bước 2/4");
  assert.equal(en("run.step", { current: 2, total: 4 }), "Step 2/4");
  assert.equal(en("run.step"), "Step {current}/{total}");
  assert.equal(en("no.such.key"), "no.such.key");
});

test("an unknown or missing stored language means the default, and storage failures are survivable", () => {
  assert.equal(resolveLocale("fr"), DEFAULT_LOCALE);
  assert.equal(resolveLocale("en"), "en");
  assert.equal(loadLocale({ getItem: () => "en" }), "en");
  assert.equal(loadLocale({ getItem: () => null }), DEFAULT_LOCALE);
  assert.equal(loadLocale({ getItem: () => { throw new Error("blocked"); } }), DEFAULT_LOCALE);
  const written = {};
  saveLocale({ setItem: (key, value) => { written[key] = value; } }, "en");
  assert.deepEqual(written, { [LOCALE_STORAGE_KEY]: "en" });
  assert.doesNotThrow(() => saveLocale({ setItem: () => { throw new Error("blocked"); } }, "en"));
});

test("shortcut actions and groups are all named in both languages", () => {
  for (const locale of ["vi", "en"]) for (const action of ACTIONS) {
    assert.ok(MESSAGES[locale][`shortcut.${action.id}`], `${locale} ${action.id}`);
    assert.ok(MESSAGES[locale][`shortcut.group.${action.group}`], `${locale} ${action.group}`);
  }
});

test("run progress text follows the chosen language", () => {
  const vi = createTranslator("vi"), en = createTranslator("en");
  const paused = reduceRunEvent(initialRunState(), { id: "1", type: "APPROVAL_REQUIRED", run_id: "r", payload: { approval_id: "a" } });
  assert.equal(liveActivity(paused, vi), "Đang chờ bạn duyệt");
  assert.equal(liveActivity(paused, en), "Waiting for your approval");
  assert.equal(stepLabel(initialRunState(), 4, en), "Step 1/4");
  const coded = reduceRunEvent(initialRunState(), { id: "2", type: "AUTOGEN_CODE_GENERATED", payload: { code: "print(1)" } });
  assert.equal(liveActivity(coded, en), "Wrote code to verify the result");
});

test("status names and date formats are localised, unknown statuses pass through", () => {
  assert.equal(statusLabel(createTranslator("en"), "completed"), "Completed");
  assert.equal(statusLabel(createTranslator("vi"), "completed"), "Hoàn tất");
  assert.equal(statusLabel(createTranslator("en"), "weird"), "weird");
  assert.equal(dateLocale("vi"), "vi-VN");
  assert.equal(dateLocale("en"), "en-GB");
});
