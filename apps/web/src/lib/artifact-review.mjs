import { lineDiff } from "./workspace.mjs";

/** Contiguous changes form a hunk; unchanged lines stay outside the review decision. */
export function reviewSections(before, after) {
  const sections = [];
  let hunk = 0;
  for (const op of lineDiff(before ?? "", after)) {
    const changed = op.type !== "same";
    let section = sections.at(-1);
    if (!section || section.changed !== changed) {
      section = { id: changed ? String(hunk++) : `context-${sections.length}`, changed, ops: [] };
      sections.push(section);
    }
    section.ops.push(op);
  }
  return sections;
}

/** Pending changes are retained; rejecting a hunk keeps its original lines exactly. */
export function reviewedContent(before, after, decisions) {
  return reviewSections(before, after).flatMap((section) => {
    const rejected = decisions[section.id] === "rejected";
    return section.ops.filter((op) => rejected ? op.type !== "add" : op.type !== "del").map((op) => op.text);
  }).join("\n");
}

/** Match the saved state of a completed step, never silently substitute the latest snapshot. */
export function checkpointForStep(checkpoints, nodeId) {
  return checkpoints.find((checkpoint) => {
    const completed = checkpoint.state.completed_nodes;
    return Array.isArray(completed) && completed.at(-1) === nodeId;
  }) ?? null;
}
