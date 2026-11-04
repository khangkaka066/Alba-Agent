// Model selector helpers: which model is active, how the list is grouped, and what is remembered between visits.

export const MODEL_STORAGE_KEY = "nexus_model";

/** Short name for a `provider/model` id: the model part, without the provider prefix. */
export function modelLabel(id) {
  if (typeof id !== "string" || !id) return "";
  const cut = id.indexOf("/");
  return cut === -1 ? id : id.slice(cut + 1);
}

/** Splits a typed `provider/model` id; null when it does not have that shape. */
export function parseModelId(text) {
  const match = /^([a-z][a-z0-9_-]{1,40})\/([A-Za-z0-9][\w.:/@+-]{0,150})$/.exec(typeof text === "string" ? text.trim() : "");
  return match ? { provider: match[1], model: match[2], id: `${match[1]}/${match[2]}` } : null;
}

/**
 * The id to use: the remembered choice while it can still run (it is listed, or a model typed by the user whose provider is
 * connected), otherwise the server's default, otherwise the first model.
 */
export function resolveSelection(models, remembered, serverDefault, reachableProviders = []) {
  const ids = Array.isArray(models) ? models.map((item) => item.id) : [];
  if (remembered && ids.includes(remembered)) return remembered;
  const typed = parseModelId(remembered);
  if (typed && reachableProviders.includes(typed.provider)) return typed.id;
  if (serverDefault && ids.includes(serverDefault)) return serverDefault;
  return ids[0] ?? null;
}

/** Models grouped by provider label in the order the server listed them; models on this machine come first. */
export function groupModels(models) {
  const groups = [];
  for (const model of Array.isArray(models) ? models : []) {
    let group = groups.find((item) => item.name === model.group);
    if (!group) { group = { name: model.group, local: Boolean(model.local), models: [] }; groups.push(group); }
    group.models.push(model);
  }
  return groups.sort((a, b) => Number(b.local) - Number(a.local));
}

export function loadModel(storage) {
  try { return storage.getItem(MODEL_STORAGE_KEY) || null; } catch { return null; }
}

export function saveModel(storage, id) {
  try { if (id) storage.setItem(MODEL_STORAGE_KEY, id); else storage.removeItem(MODEL_STORAGE_KEY); } catch { /* the choice then lasts for this visit only */ }
}

const RECENT_KEY = "nexus_recent_models";

/** The last few models the person chose, newest first. */
export function loadRecent(storage) {
  try {
    const parsed = JSON.parse(storage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string").slice(0, 5) : [];
  } catch { return []; }
}

export function rememberRecent(storage, id, limit = 3) {
  try { storage.setItem(RECENT_KEY, JSON.stringify([id, ...loadRecent(storage).filter((item) => item !== id)].slice(0, limit))); } catch { /* the shortcut list then resets next visit */ }
}

/**
 * What the picker shows, kept short however many providers are connected: the models the person used last (only ones that
 * still run), then one collapsed row per provider with its model count. A search replaces both with one flat list of matches.
 */
export function pickerView(models, recent, query = "") {
  const list = Array.isArray(models) ? models : [];
  const needle = String(query).trim().toLowerCase();
  if (needle) {
    const matches = list.filter((item) => `${item.group} ${item.model} ${item.id}`.toLowerCase().includes(needle));
    return { recent: [], providers: [], matches };
  }
  const byId = new Map(list.map((item) => [item.id, item]));
  return {
    recent: (Array.isArray(recent) ? recent : []).map((id) => byId.get(id)).filter(Boolean),
    providers: groupModels(list),
    matches: [],
  };
}
