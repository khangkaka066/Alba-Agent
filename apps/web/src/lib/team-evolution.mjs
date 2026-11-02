/** Pure helpers for team generations: graph-diff statuses, fitness trendline geometry and labels. */

export const DIFF_LABELS = { added: "New", modified: "Changed", removed: "Pruned" };
export const POLICY_LABELS = { SUGGEST_FIRST: "Suggest first", FULLY_AUTONOMOUS: "Fully autonomous" };

/** Map each node id touched by a generation to how it changed: emerald (added), amber (modified), rose (removed). */
export function diffStatuses(diff) {
  const statuses = {};
  for (const id of diff?.modified_nodes ?? []) statuses[id] = "modified";
  for (const id of diff?.added_nodes ?? []) statuses[id] = "added";
  for (const id of diff?.removed_nodes ?? []) statuses[id] = "removed";
  return statuses;
}

/** Human-readable lines for a proposal card, mirroring the canvas colours. */
export function diffLines(diff) {
  const lines = [];
  for (const id of diff?.added_nodes ?? []) lines.push({ tone: "added", text: `+ Added node ${id}` });
  for (const [node, roles] of Object.entries(diff?.added_agents ?? {})) for (const role of roles) lines.push({ tone: "added", text: `+ Added ${role} in ${node}` });
  for (const id of diff?.modified_nodes ?? []) lines.push({ tone: "modified", text: `~ Changed node ${id}` });
  for (const [node, roles] of Object.entries(diff?.removed_agents ?? {})) for (const role of roles) lines.push({ tone: "removed", text: `- Pruned ${role} from ${node}` });
  for (const id of diff?.removed_nodes ?? []) lines.push({ tone: "removed", text: `- Pruned node ${id}` });
  return lines;
}

/** Nodes the previous generation had that the new one removed, so the canvas can ghost them in rose. */
export function removedNodes(parentSpec, diff) {
  const removed = new Set(diff?.removed_nodes ?? []);
  return (Array.isArray(parentSpec?.nodes) ? parentSpec.nodes : []).filter((node) => removed.has(node.id));
}

export function removedEdges(parentSpec, diff) {
  const removed = new Set(diff?.removed_nodes ?? []);
  return (Array.isArray(parentSpec?.edges) ? parentSpec.edges : []).filter((edge) => removed.has(edge.source) || removed.has(edge.target));
}

/** SVG polyline for the fitness trend of a lineage (versions on x, fitness 0..1 on y). */
export function trendGeometry(trend, width, height, pad = 12) {
  const points = (Array.isArray(trend) ? trend : []).filter((item) => typeof item.fitness === "number");
  if (!points.length) return { points: [], path: "" };
  const span = Math.max(1, points.length - 1);
  const placed = points.map((item, index) => ({
    version: item.version, fitness: item.fitness,
    x: points.length === 1 ? width / 2 : pad + (index / span) * (width - 2 * pad),
    y: pad + (1 - Math.min(1, Math.max(0, item.fitness))) * (height - 2 * pad),
  }));
  return { points: placed, path: placed.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ") };
}

export function fitnessDelta(generation, parent) {
  if (typeof generation?.fitness !== "number" || typeof parent?.fitness !== "number") return null;
  return generation.fitness - parent.fitness;
}

export function lineageLabel(generations) {
  return (Array.isArray(generations) ? generations : []).filter((item) => item.status !== "rejected").map((item) => `v${item.version}`).join(" → ");
}
