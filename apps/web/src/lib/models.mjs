// Model selector helpers: which model is active, how the list is grouped, and what is remembered between visits.

export const MODEL_STORAGE_KEY = "nexus_model";

// Split only explicit account variants advertised with matching effort suffixes.
// API model ids and names such as "mini" or "Thinking" keep their original identity.
function variant(model) {
  const id = /^(.*\/nexus-account-[a-z]+:.+)[-@](none|minimal|low|medium|high|xhigh|extra|max|ultra)$/.exec(model.id);
  const label = /^(.*)\s+\((None|Minimal|Low|Medium|High|Xhigh|Extra|Max|Ultra)\)$/.exec(model.model);
  if (!id || !label || id[2] !== label[2].toLowerCase()) return { key: model.id, name: model.model, effort: null, label: null };
  return { key: id[1], name: label[1], effort: id[2], label: label[2] };
}

/** One row per model, retaining the selected concrete account id for dispatch. */
export function modelChoices(models, selected) {
  const choices = new Map();
  for (const model of models) {
    const family = variant(model);
    if (!choices.has(family.key) || model.id === selected) choices.set(family.key, { ...model, model: family.name });
  }
  return [...choices.values()];
}

/** Only efforts actually advertised for this exact provider/account model. */
export function effortChoices(models, selected) {
  const current = models.find((model) => model.id === selected);
  if (!current) return [];
  const key = variant(current).key;
  const order = ["none", "minimal", "low", "medium", "high", "xhigh", "extra", "max", "ultra"];
  return models.filter((model) => variant(model).key === key && variant(model).effort !== null)
    .map((model) => ({ id: model.id, value: variant(model).effort, label: variant(model).label }))
    .sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value));
}

/** Keep effort when switching to another model that supports the same level. */
export function preferredModelVariant(models, target, selected) {
  const effort = effortChoices(models, selected).find((item) => item.id === selected)?.value;
  return effortChoices(models, target).find((item) => item.value === effort)?.id ?? target;
}

/** Short name for a `provider/model` id: the model part, without the provider prefix. */
export function modelLabel(id) {
  if (typeof id !== "string" || !id) return "";
  const account = /(?:^|\/)nexus-account-(codex|claude|gemini):default$/.exec(id);
  if (account) return ({codex:"ChatGPT",claude:"Claude",gemini:"Gemini"})[account[1]];
  const specific = /(?:^|\/)nexus-account-(?:codex|claude|gemini):(.+)$/.exec(id);
  if (specific) return specific[1];
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
  if (typeof remembered === "string" && remembered.includes("/nexus-account-copilot:")) remembered = null;
  const ids = Array.isArray(models) ? models.map((item) => item.id) : [];
  if (remembered && ids.includes(remembered)) return remembered;
  if (typeof remembered === "string" && /\/nexus-account-[a-z]+:default$/.test(remembered)) {
    const prefix = remembered.slice(0, -"default".length);
    const migrated = ids.find((id) => id.startsWith(prefix));
    if (migrated) return migrated;
  }
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
