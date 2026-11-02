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
