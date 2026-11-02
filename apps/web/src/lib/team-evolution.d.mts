export type DiffStatus = "added" | "modified" | "removed";
export type TopologyDiff = {
  added_nodes?: string[]; modified_nodes?: string[]; removed_nodes?: string[];
  added_agents?: Record<string, string[]>; removed_agents?: Record<string, string[]>;
};
export const DIFF_LABELS: Record<DiffStatus, string>;
export const POLICY_LABELS: Record<string, string>;
export function diffStatuses(diff: TopologyDiff | undefined | null): Record<string, DiffStatus>;
export function diffLines(diff: TopologyDiff | undefined | null): Array<{ tone: DiffStatus; text: string }>;
export function removedNodes(parentSpec: unknown, diff: TopologyDiff | undefined | null): Array<Record<string, unknown> & { id: string }>;
export function removedEdges(parentSpec: unknown, diff: TopologyDiff | undefined | null): Array<Record<string, unknown> & { source: string; target: string }>;
export function trendGeometry(trend: unknown, width: number, height: number, pad?: number): { points: Array<{ version: number; fitness: number; x: number; y: number }>; path: string };
export function fitnessDelta(generation: { fitness?: number | null } | undefined, parent: { fitness?: number | null } | undefined): number | null;
export function lineageLabel(generations: Array<{ version: number; status: string }>): string;
