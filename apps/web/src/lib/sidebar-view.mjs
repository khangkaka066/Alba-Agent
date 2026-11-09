// Device-local sidebar state; server account scope is part of the storage key.
export const SIDEBAR_DEFAULTS = { groupBy: "project", conversationSort: "updated", projectSort: "custom", filter: "all", query: "", compact: true, showTime: true, showStatus: true, autoPin: false, archivedOnly: false, projectOrder: [], archived: {}, pinned: {}, seen: {}, initialized: false };
const enums = { groupBy: ["project", "none"], conversationSort: ["updated", "created", "name"], projectSort: ["custom", "updated", "name"], filter: ["all", "active", "attention", "completed", "unread"] };
export function normalizeSidebar(value) {
  const input = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const result = { ...SIDEBAR_DEFAULTS };
  for (const [key, choices] of Object.entries(enums)) if (choices.includes(input[key])) result[key] = input[key];
  for (const key of ["compact", "showTime", "showStatus", "autoPin", "archivedOnly", "initialized"]) if (typeof input[key] === "boolean") result[key] = input[key];
  result.query = typeof input.query === "string" ? input.query.slice(0, 200) : "";
  result.projectOrder = Array.isArray(input.projectOrder) ? [...new Set(input.projectOrder.filter(x => typeof x === "string" && x))].slice(0, 500) : [];
  for (const key of ["archived", "pinned", "seen"]) {
    const map = input[key];
    result[key] = map && typeof map === "object" && !Array.isArray(map) ? Object.fromEntries(Object.entries(map).filter(([id, value]) => id && (key === "seen" ? typeof value === "number" && Number.isFinite(value) && value >= 0 : value === true)).slice(-2000)) : {};
  }
  return result;
}
export function loadSidebar(storage, key) { try { return normalizeSidebar(JSON.parse(storage.getItem(key) ?? "null")); } catch { return normalizeSidebar(null); } }
export function saveSidebar(storage, key, value) { try { storage.setItem(key, JSON.stringify(normalizeSidebar(value))); } catch { /* Settings remain usable for this session. */ } }
export function conversationKey(item) { return item.run.conversation_id || item.run.id; }
export function conversationTime(item, field = "updated") {
  const run = item.run;
  const values = field === "created" ? [run.created_at] : [run.updated_at, run.finished_at, run.started_at, run.created_at];
  return Math.max(0, ...values.map(value => Date.parse(value || "")).filter(Number.isFinite));
}
export function isUnread(item, state) { return state.initialized && conversationTime(item) > (state.seen[conversationKey(item)] ?? 0); }
export function readConversations(state, items) {
  const seen = { ...state.seen };
  for (const item of items) { const key = conversationKey(item); seen[key] = Math.max(seen[key] || 0, conversationTime(item)); }
  return { ...state, initialized: true, seen };
}
export function isActive(item) { return ["running", "queued", "paused"].includes(item.run.status); }
export function sidebarItems(items, state) {
  const query = state.query.trim().toLocaleLowerCase();
  return items.filter(item => {
    if (Boolean(state.archived[conversationKey(item)]) !== state.archivedOnly) return false;
    if (query && !item.name.toLocaleLowerCase().includes(query)) return false;
    if (state.filter === "active") return ["running", "queued"].includes(item.run.status);
    if (state.filter === "attention") return ["paused", "failed"].includes(item.run.status);
    if (state.filter === "completed") return ["completed", "chat"].includes(item.run.status);
    return state.filter !== "unread" || isUnread(item, state);
  }).sort((a, b) => {
    const pin = item => Boolean(state.pinned[conversationKey(item)] || state.autoPin && isActive(item));
    const pinned = Number(pin(b)) - Number(pin(a));
    if (pinned) return pinned;
    if (state.conversationSort === "name") return a.name.localeCompare(b.name) || a.run.id.localeCompare(b.run.id);
    const field = state.conversationSort === "created" ? "created" : "updated";
    return conversationTime(b, field) - conversationTime(a, field) || a.run.id.localeCompare(b.run.id);
  });
}
export function sortSidebarProjects(groups, state) {
  const order = new Map(state.projectOrder.map((name, index) => [name, index]));
  return [...groups].sort((a, b) => {
    if (state.projectSort === "name") return a.name.localeCompare(b.name);
    if (state.projectSort === "updated") return Math.max(0, ...b.tasks.map(item => conversationTime(item))) - Math.max(0, ...a.tasks.map(item => conversationTime(item)));
    return (order.get(a.name) ?? state.projectOrder.length) - (order.get(b.name) ?? state.projectOrder.length);
  });
}
export function moveSidebarProject(names, name, direction) {
  const result = [...names], index = result.indexOf(name), target = index + direction;
  if (index >= 0 && target >= 0 && target < result.length) [result[index], result[target]] = [result[target], result[index]];
  return result;
}
