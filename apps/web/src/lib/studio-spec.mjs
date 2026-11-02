/** Pure helpers for the hierarchical studio canvas: tier grouping, rigor choices and router rule text. */

export const RIGOR_OPTIONS = [
  { value: "auto", label: "Auto · match the request" },
  { value: "minimal", label: "Minimal (4 Agents)" },
  { value: "standard", label: "Departmental (16 Agents)" },
  { value: "full_studio", label: "Full Studio (30-50 Agents)" },
];

export const TIER_LABELS = { director: "Tier 1: Director", lead: "Tier 2: Lead", specialist: "Tier 3: Specialists" };
const TIER_ORDER = ["director", "lead", "specialist"];

function list(value) {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}

/** Group a crew's agents by tier and attach the artifact paths each agent is responsible for. */
export function groupAgentsByTier(agents, tasks) {
  const pathsByAgent = new Map();
  for (const task of Array.isArray(tasks) ? tasks : []) {
    if (!task || typeof task.agent_id !== "string") continue;
    const owned = pathsByAgent.get(task.agent_id) ?? [];
    for (const path of list(task.expected_artifact_paths)) if (!owned.includes(path)) owned.push(path);
    pathsByAgent.set(task.agent_id, owned);
  }
  const groups = { director: [], lead: [], specialist: [], untiered: [] };
  for (const agent of Array.isArray(agents) ? agents : []) {
    if (!agent || typeof agent !== "object") continue;
    const entry = {
      id: String(agent.id ?? ""),
      role: String(agent.role ?? "Agent"),
      model: String(agent.model ?? ""),
      skills: list(agent.skill_ids),
      tools: list(agent.tool_ids),
      paths: pathsByAgent.get(String(agent.id ?? "")) ?? [],
    };
    (TIER_ORDER.includes(agent.tier) ? groups[agent.tier] : groups.untiered).push(entry);
  }
  return groups;
}

export function hasTiers(groups) {
  return groups.director.length + groups.lead.length + groups.specialist.length > 0;
}

const OPERATOR_SYMBOLS = { eq: "==", ne: "!=", gt: ">", gte: ">=", lt: "<", lte: "<=", exists: "exists" };
export const OPERATOR_CODES = Object.fromEntries(Object.entries(OPERATOR_SYMBOLS).map(([code, symbol]) => [symbol, code]));

/** Render router routes as the editable `field op value → route` lines the canvas drawer uses. */
export function routesToText(routes) {
  return (Array.isArray(routes) ? routes : []).map((route) => {
    const symbol = OPERATOR_SYMBOLS[route.operator] ?? "==";
    const value = symbol === "exists" ? "" : ` ${typeof route.value === "string" ? route.value : JSON.stringify(route.value)}`;
    return `${route.field_path} ${symbol}${value} → ${route.name}`;
  }).join("\n");
}

export function parseJsonList(value) {
  try {
    const parsed = JSON.parse(value ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}
