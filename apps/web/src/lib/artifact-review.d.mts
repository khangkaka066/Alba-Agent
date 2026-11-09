import type { DiffOp } from "./workspace.mjs";
export type HunkDecision = "accepted" | "rejected";
export type Checkpoint = { id: string; sequence: number; created_at: string; state: Record<string, unknown> };
export function reviewSections(before: string | null, after: string): Array<{ id: string; changed: boolean; ops: DiffOp[] }>;
export function reviewedContent(before: string | null, after: string, decisions: Record<string, HunkDecision>): string;
export function checkpointForStep(checkpoints: Checkpoint[], nodeId: string): Checkpoint | null;
