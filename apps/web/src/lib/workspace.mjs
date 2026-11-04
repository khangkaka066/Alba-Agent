// Pure helpers for the Cursor-style workspace: artifact kinds, file tree, line diff, run-event reducer, team summary.
import { createTranslator } from "./i18n.mjs";

const vi = createTranslator("vi");

const CODE = new Set(["py", "ts", "tsx", "js", "jsx", "mjs", "json", "yaml", "yml", "toml", "sh", "sql", "css", "html", "go", "rs", "java", "c", "h", "cpp", "rb", "php", "swift", "kt", "xml", "ini", "cfg"]);
const DOCUMENT = new Set(["md", "txt", "csv", "log", "rst", "tsv"]);
const IMAGE = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "avif"]);
const VIDEO = new Set(["mp4", "webm", "mov", "m4v"]);
const AUDIO = new Set(["mp3", "wav", "ogg", "m4a", "flac"]);

export const extensionOf = (name) => { const base = String(name).split("/").pop() ?? ""; const dot = base.lastIndexOf("."); return dot > 0 ? base.slice(dot + 1).toLowerCase() : ""; };

/** `kind` drives which viewer opens; `text` means the content can be shown and diffed as text. */
export function classifyArtifact(filename, mime = "") {
  const ext = extensionOf(filename);
  if (VIDEO.has(ext) || mime.startsWith("video/")) return { kind: "video", text: false };
  if (IMAGE.has(ext) || mime.startsWith("image/")) return { kind: "image", text: false };
  if (AUDIO.has(ext) || mime.startsWith("audio/")) return { kind: "audio", text: false };
  if (CODE.has(ext)) return { kind: "code", text: true };
  if (DOCUMENT.has(ext) || mime.startsWith("text/")) return { kind: "document", text: true };
  if (ext === "pdf") return { kind: "pdf", text: false };
  return { kind: "other", text: false };
}

/** Nested tree, directories first then files, each alphabetically. `statuses` maps a path to "added" | "modified". */
export function buildTree(paths, statuses = {}) {
  const root = { name: "", path: "", kind: "dir", children: [] };
  for (const path of [...new Set(paths)].filter(Boolean)) {
    const parts = path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, index) => {
      const full = parts.slice(0, index + 1).join("/");
      const isFile = index === parts.length - 1;
      let child = node.children.find((item) => item.name === part && item.kind === (isFile ? "file" : "dir"));
      if (!child) { child = isFile ? { name: part, path: full, kind: "file", status: statuses[full] } : { name: part, path: full, kind: "dir", children: [] }; node.children.push(child); }
      node = child;
    });
  }
  const order = (items) => {
    items.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1));
    for (const item of items) if (item.children) order(item.children);
  };
  order(root.children);
  return root.children;
}

/** Whether each current file is new or changed compared with an earlier snapshot ({path: size|hash}). */
export function fileStatuses(current, previous) {
  const result = {};
  for (const [path, signature] of Object.entries(current)) {
    if (!(path in previous)) result[path] = "added";
    else if (previous[path] !== signature) result[path] = "modified";
  }
  return result;
}

const MAX_DIFF_CELLS = 4_000_000;

/** Line diff by longest common subsequence: [{ type: "same" | "add" | "del", text, oldNo, newNo }]. */
export function lineDiff(before, after) {
  const a = before === "" ? [] : before.split("\n");
  const b = after === "" ? [] : after.split("\n");
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
  let endA = a.length; let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA -= 1; endB -= 1; }
  const midA = a.slice(start, endA); const midB = b.slice(start, endB);
  const ops = [];
  for (let i = 0; i < start; i += 1) ops.push({ type: "same", text: a[i], oldNo: i + 1, newNo: i + 1 });
  if (midA.length * midB.length > MAX_DIFF_CELLS) {
    midA.forEach((text, i) => ops.push({ type: "del", text, oldNo: start + i + 1, newNo: null }));
    midB.forEach((text, i) => ops.push({ type: "add", text, oldNo: null, newNo: start + i + 1 }));
  } else {
    const width = midB.length + 1;
    const table = new Uint32Array((midA.length + 1) * width);
    for (let i = midA.length - 1; i >= 0; i -= 1) for (let j = midB.length - 1; j >= 0; j -= 1) {
      table[i * width + j] = midA[i] === midB[j] ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
    }
    let i = 0; let j = 0;
    while (i < midA.length && j < midB.length) {
      if (midA[i] === midB[j]) { ops.push({ type: "same", text: midA[i], oldNo: start + i + 1, newNo: start + j + 1 }); i += 1; j += 1; }
      else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) { ops.push({ type: "del", text: midA[i], oldNo: start + i + 1, newNo: null }); i += 1; }
      else { ops.push({ type: "add", text: midB[j], oldNo: null, newNo: start + j + 1 }); j += 1; }
    }
    for (; i < midA.length; i += 1) ops.push({ type: "del", text: midA[i], oldNo: start + i + 1, newNo: null });
    for (; j < midB.length; j += 1) ops.push({ type: "add", text: midB[j], oldNo: null, newNo: start + j + 1 });
  }
  const tail = a.length - endA;
  for (let k = 0; k < tail; k += 1) ops.push({ type: "same", text: a[endA + k], oldNo: endA + k + 1, newNo: endB + k + 1 });
  return ops;
}

export const diffStats = (ops) => ({ added: ops.filter((op) => op.type === "add").length, removed: ops.filter((op) => op.type === "del").length });

/** Side-by-side rows: a run of deletions is paired with the additions that follow it. */
export function splitRows(ops) {
  const rows = [];
  let index = 0;
  while (index < ops.length) {
    const op = ops[index];
    if (op.type === "same") { rows.push({ left: op, right: op }); index += 1; continue; }
    const dels = []; const adds = [];
    while (index < ops.length && ops[index].type === "del") { dels.push(ops[index]); index += 1; }
    while (index < ops.length && ops[index].type === "add") { adds.push(ops[index]); index += 1; }
    for (let k = 0; k < Math.max(dels.length, adds.length); k += 1) rows.push({ left: dels[k] ?? null, right: adds[k] ?? null });
  }
  return rows;
}

/** Agents, tiers and departments of a generated WorkflowSpec, for the "Active Agent Team" pill. */
export function teamSummary(spec) {
  const nodes = Array.isArray(spec?.nodes) ? spec.nodes : [];
  let agents = 0; let sandboxes = 0; let crews = 0;
  const tiers = {};
  for (const node of nodes) {
    if (node.kind === "crew") {
      crews += 1;
      for (const agent of Array.isArray(node.agents) ? node.agents : []) { agents += 1; const tier = String(agent.tier ?? "specialist"); tiers[tier] = (tiers[tier] ?? 0) + 1; }
    } else if (node.kind === "sandbox") { sandboxes += 1; agents += 2; tiers.specialist = (tiers.specialist ?? 0) + 2; }
  }
  const steps = nodes.filter((node) => node.kind !== "start").length;
  const label = Object.keys(tiers).length > 1 ? "Director → Department crews → Sandbox" : crews && sandboxes ? "Crew → Sandbox" : crews ? "Crew" : sandboxes ? "Sandbox" : "Workflow";
  return { agents, crews, sandboxes, steps, tiers, label, rigor: spec?.modes?.rigor ?? null };
}

export const initialRunState = () => ({ status: "idle", completed: [], active: [], terminal: [], thoughts: [], tools: [], approvals: [], resolved: [], frame: "", error: "" });

const keep = (list, item, limit) => [...list, item].slice(-limit);

/** Folds one runtime event into the run state shown by the composer, terminal and canvas pill. */
export function reduceRunEvent(state, event) {
  const p = event.payload ?? {};
  const node = String(p.node_id ?? event.node_id ?? "");
  switch (event.type) {
    case "FLOW_STATE_CHANGED": {
      if (p.status === "running") return { ...state, status: state.status === "paused" ? "running" : "running", active: [...new Set([...state.active, node])] };
      if (p.status === "completed") return { ...state, active: state.active.filter((id) => id !== node), completed: [...new Set([...state.completed, node])] };
      return state;
    }
    case "CREW_AGENT_THOUGHT": return { ...state, thoughts: keep(state.thoughts, { id: event.id, node, text: String(p.content ?? p.thought ?? p.message ?? "") }, 80) };
    case "NEXUSGEN_CODE_GENERATED": return { ...state, thoughts: keep(state.thoughts, { id: event.id, node, text: "", textKey: "run.codeWritten", code: String(p.code ?? p.content ?? "") }, 80) };
    case "TOOL_INVOKED": return { ...state, tools: keep(state.tools, { id: event.id, node, name: String(p.tool ?? p.name ?? "tool") }, 80) };
    case "SANDBOX_TERMINAL_OUTPUT": return { ...state, terminal: keep(state.terminal, { id: event.id, stream: String(p.stream ?? "stdout"), text: String(p.content ?? p.output ?? "") }, 400) };
    case "SANDBOX_SCREEN_FRAME": return { ...state, frame: typeof p.data_base64 === "string" ? `data:${String(p.mime_type ?? "image/png")};base64,${p.data_base64}` : state.frame };
    case "APPROVAL_REQUIRED": return { ...state, status: "paused", approvals: typeof p.approval_id === "string" && !state.approvals.some((a) => a.approval_id === p.approval_id) ? [...state.approvals, { approval_id: p.approval_id, run_id: event.run_id, node_id: node || undefined, action: String(p.action ?? "Review action"), rationale: typeof p.rationale === "string" ? p.rationale : undefined, kind: typeof p.kind === "string" ? p.kind : undefined }] : state.approvals };
    case "APPROVAL_RESOLVED": return { ...state, status: "running", resolved: typeof p.approval_id === "string" ? [...state.resolved, p.approval_id] : state.resolved, approvals: state.approvals.filter((a) => a.approval_id !== p.approval_id) };
    case "RUN_COMPLETED": return { ...state, status: "completed", active: [] };
    case "RUN_FAILED": return { ...state, status: "failed", active: [], error: String(p.message ?? p.error_type ?? "runtime error") };
    default: return state;
  }
}

export const isFinished = (status) => status === "completed" || status === "failed";

/** "Step 3/6" style progress from completed nodes and the spec's step count. */
export function stepLabel(state, steps, t = vi) {
  if (!steps) return "";
  return t("run.step", { current: Math.min(state.completed.length + (isFinished(state.status) ? 0 : 1), steps), total: steps });
}

/** A human line for the composer: what the swarm is doing right now. */
export function liveActivity(state, t = vi) {
  if (state.status === "paused") return t("run.waitingApproval");
  if (state.status === "completed") return t("run.done");
  if (state.status === "failed") return t("run.failedWith", { error: state.error });
  const last = state.thoughts[state.thoughts.length - 1];
  if (last?.textKey) return t(last.textKey);
  return last?.text ? last.text.slice(0, 140) : state.active.length ? t("run.processing", { node: state.active[0] }) : t("run.assembling");
}

/** Splits text files into the flat set the sandbox accepts, with a manifest mapping flat names back to real paths. */
export function flattenWorkspaceFiles(files, budget = 900_000) {
  const flat = {}; const map = {}; let used = 0;
  for (const file of files) {
    const base = file.path.split("/").pop();
    if (!base || base.startsWith(".")) continue;
    let name = base; let n = 1;
    while (name in flat) { n += 1; const dot = base.lastIndexOf("."); name = dot > 0 ? `${base.slice(0, dot)}_${n}${base.slice(dot)}` : `${base}_${n}`; }
    const size = new TextEncoder().encode(file.content).byteLength;
    if (used + size > budget) continue;
    flat[name] = file.content; map[name] = file.path; used += size;
  }
  const manifest = JSON.stringify({ note: "Files are mounted flat in the working directory. Edit a file by writing the same name; the owner maps it back to its real path.", files: map }, null, 2);
  if (used + manifest.length <= budget + 50_000) flat["workspace_manifest.json"] = manifest;
  return { files: flat, map, bytes: used };
}
