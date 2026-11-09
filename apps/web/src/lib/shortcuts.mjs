// Keyboard shortcuts: defaults, combo parsing, validation and persistence. Pure so it can be unit tested.
// A combo is a string such as "Mod+K" or "Mod+Shift+Enter"; "Mod" is Cmd on macOS and Ctrl elsewhere.

export const STORAGE_KEY = "nexus_shortcuts";

// Display names live in the message tables under `shortcut.<id>` and `shortcut.group.<group>`.
export const ACTIONS = [
  { id: "palette", group: "general", default: "Mod+Shift+P" },
  { id: "new-conversation", group: "general", default: "Mod+Shift+N" },
  { id: "open-terminal", group: "general", default: "Mod+Shift+T" },
  { id: "toggle-sidebar", group: "general", default: "Mod+B" },
  { id: "toggle-canvas", group: "general", default: "Mod+\\" },
  { id: "run", group: "general", default: "Mod+Enter" },
  { id: "toggle-dock", group: "general", default: "Mod+J" },
  { id: "toggle-inspector", group: "general", default: "Mod+I" },
  { id: "focus-composer", group: "general", default: "Mod+L" },
  { id: "mode-mission", group: "navigation", default: "Mod+1" },
  { id: "mode-editor", group: "navigation", default: "Mod+2" },
  { id: "mode-canvas", group: "navigation", default: "Mod+3" },
  { id: "toggle-workbench", group: "navigation", default: "Mod+E" },
  { id: "nav-studio", group: "navigation", default: "Mod+Shift+1" },
  { id: "nav-integrations", group: "navigation", default: "Mod+Shift+2" },
  { id: "nav-settings", group: "navigation", default: "Mod+," },
];

export const DEFAULT_BINDINGS = Object.fromEntries(ACTIONS.map((action) => [action.id, action.default]));

const MODIFIER_KEYS = new Set(["Meta", "Control", "Alt", "Shift", "AltGraph", "OS"]);
const NAMED_KEYS = { " ": "Space", Esc: "Escape", Up: "ArrowUp", Down: "ArrowDown", Left: "ArrowLeft", Right: "ArrowRight" };

/** Combo for a keyboard event, or "" while only a modifier is held. */
export function comboFromEvent(event) {
  if (MODIFIER_KEYS.has(event.key)) return "";
  const raw = NAMED_KEYS[event.key] ?? event.key;
  const key = raw.length === 1 ? raw.toUpperCase() : raw;
  const parts = [];
  if (event.metaKey || event.ctrlKey) parts.push("Mod");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  return [...parts, key].join("+");
}

/** Plain typing must keep working, so a binding needs Mod or Alt (or a function key). Escape is reserved for closing dialogs. */
export function isValidCombo(combo) {
  if (typeof combo !== "string" || !combo) return false;
  const parts = combo.split("+");
  const key = parts[parts.length - 1];
  if (!key || key === "Escape" || key === "Mod" || key === "Alt" || key === "Shift") return false;
  if (/^F([1-9]|1[0-2])$/.test(key)) return true;
  return parts.includes("Mod") || parts.includes("Alt");
}

export function formatCombo(combo, mac) {
  if (!combo) return "";
  const symbols = mac
    ? { Mod: "⌘", Alt: "⌥", Shift: "⇧", Enter: "↵", Escape: "Esc", ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→" }
    : { Mod: "Ctrl", Alt: "Alt", Shift: "Shift", Enter: "Enter", ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→" };
  return combo.split("+").map((part) => symbols[part] ?? part).join(mac ? " " : "+");
}

/** Defaults overlaid with saved overrides. An invalid override, or one that collides with another binding, is dropped. */
export function resolveBindings(saved) {
  const result = { ...DEFAULT_BINDINGS };
  if (!saved || typeof saved !== "object") return result;
  for (const action of ACTIONS) if (saved[action.id] === "" || isValidCombo(saved[action.id])) result[action.id] = saved[action.id];
  // Each pass reverts the later of two colliding actions to its default; defaults are unique, so this settles.
  for (let pass = 0; pass < ACTIONS.length; pass += 1) {
    const owner = new Map();
    let changed = false;
    for (const action of ACTIONS) {
      const combo = result[action.id];
      if (!combo) continue;
      if (owner.has(combo) && combo !== DEFAULT_BINDINGS[action.id]) { result[action.id] = DEFAULT_BINDINGS[action.id]; changed = true; }
      else if (owner.has(combo)) { result[owner.get(combo)] = DEFAULT_BINDINGS[owner.get(combo)]; changed = true; owner.set(combo, action.id); }
      else owner.set(combo, action.id);
    }
    if (!changed) break;
  }
  return result;
}

/** The other action that already uses this combo, if any. */
export function findConflict(bindings, actionId, combo) {
  if (!combo) return null;
  return ACTIONS.find((action) => action.id !== actionId && bindings[action.id] === combo)?.id ?? null;
}

/** Only keep what differs from the defaults so new defaults still reach people who never customised. */
export function overridesOf(bindings) {
  return Object.fromEntries(Object.entries(bindings).filter(([id, combo]) => DEFAULT_BINDINGS[id] !== combo));
}

export function actionFor(bindings, event) {
  const combo = comboFromEvent(event);
  return combo ? ACTIONS.find((action) => bindings[action.id] === combo)?.id ?? null : null;
}

export function loadBindings(storage) {
  try { return resolveBindings(JSON.parse(storage.getItem(STORAGE_KEY) ?? "null")); } catch { return resolveBindings(null); }
}

export function saveBindings(storage, bindings) {
  try { storage.setItem(STORAGE_KEY, JSON.stringify(overridesOf(bindings))); } catch { /* private mode: the change lasts for this session only */ }
}
