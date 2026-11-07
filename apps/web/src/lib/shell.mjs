// Pure logic of the application shell: which conversations belong to which project, what the right dock shows, and
// what the dock's address bar may open. Kept free of React so it can be unit tested with node:test.

export const PROJECTS_KEY = "nexus_run_projects";
export const DOCK_TABS = ["review", "files", "terminal", "browser", "canvas"];

/** runId -> project (folder) name, remembered on this device when a task starts inside an opened folder. */
export function loadProjects(storage) {
  try {
    const parsed = JSON.parse(storage.getItem(PROJECTS_KEY) ?? "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(Object.entries(parsed).filter(([, name]) => typeof name === "string" && name));
  } catch {
    return {};
  }
}

export function rememberProject(storage, runId, name) {
  if (!runId || !name) return;
  try {
    const projects = loadProjects(storage);
    projects[runId] = name;
    // Keep the newest 500 so the entry cannot grow without bound.
    const kept = Object.fromEntries(Object.entries(projects).slice(-500));
    storage.setItem(PROJECTS_KEY, JSON.stringify(kept));
  } catch {
    /* storage can be blocked; conversations then simply stay ungrouped */
  }
}

/**
 * Projects first (in the order their newest conversation appears), then the conversations that belong to none.
 * `tasks` arrive newest first; each group keeps that order.
 */
export function groupConversations(tasks, projects) {
  const byName = new Map();
  const loose = [];
  for (const task of tasks) {
    const name = projects[task.run.id];
    if (!name) { loose.push(task); continue; }
    if (!byName.has(name)) byName.set(name, []);
    byName.get(name).push(task);
  }
  return { projects: [...byName.entries()].map(([name, items]) => ({ name, tasks: items })), loose };
}

export const INITIAL_DOCK = { open: false, tab: "files", expanded: false };

/** The dock's state machine. Showing a tab opens the dock; choosing the open tab again keeps it open (it never toggles by accident). */
export function dockAfter(state, action) {
  switch (action.type) {
    case "toggle": return { ...state, open: !state.open, expanded: state.open ? false : state.expanded };
    case "close": return { ...state, open: false, expanded: false };
    case "show": return DOCK_TABS.includes(action.tab) ? { ...state, open: true, tab: action.tab } : state;
    case "expand": return { ...state, open: true, expanded: !state.expanded };
    default: return state;
  }
}

/**
 * What the dock's address bar may open: only web pages (http or https). A bare host such as `example.com` becomes https; localhost and
 * loopback addresses stay http because that is what a dev server speaks. Anything else (javascript:, file:, data:, plain words) is refused:
 * the box never turns typed text into a request to a search engine.
 */
export function normalizeUrl(input) {
  const text = String(input ?? "").trim();
  if (!text || /\s/.test(text)) return null;
  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(text) && !/^[^/]+:\d+(\/|$)/.test(text);
  const candidate = hasScheme ? text : `${/^(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(text) ? "http" : "https"}://${text}`;
  try {
    const url = new URL(candidate);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (!url.hostname || (!url.hostname.includes(".") && !/^(localhost|\[::1\])$/i.test(url.hostname))) return null;
    return url.href;
  } catch {
    return null;
  }
}

/** Totals for the Review tab from per-file stats: [{ added, removed }] -> "+12 −3" figures. */
export function reviewTotals(stats) {
  return stats.reduce((sum, item) => ({ added: sum.added + item.added, removed: sum.removed + item.removed }), { added: 0, removed: 0 });
}

/** Plain-text title shown in the breadcrumb for a conversation: first line, trimmed, never empty. */
export function conversationTitle(name, fallback) {
  const line = String(name ?? "").split("\n")[0].trim();
  return line ? (line.length > 80 ? `${line.slice(0, 79)}…` : line) : fallback;
}
