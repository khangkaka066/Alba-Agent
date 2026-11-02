export type RunRow = { id: string; status: string; created_at: string; [key: string]: unknown };
export function statusTone(status: string): "ok" | "bad" | "busy" | "wait" | "idle";
export function orderTasks<T extends RunRow>(runs: T[] | null | undefined, currentRunId: string | null, limit?: number): T[];
export function failureFacts(failure: unknown): Array<{ key: "where" | "agent" | "message"; value: string }>;
export function failureDetails(failure: unknown): string;
