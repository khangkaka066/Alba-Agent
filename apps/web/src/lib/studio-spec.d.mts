export type TierEntry = { id: string; role: string; model: string; skills: string[]; tools: string[]; paths: string[] };
export type TierGroups = { director: TierEntry[]; lead: TierEntry[]; specialist: TierEntry[]; untiered: TierEntry[] };
export const RIGOR_OPTIONS: ReadonlyArray<{ value: "auto" | "minimal" | "standard" | "full_studio"; label: string }>;
export const TIER_LABELS: { director: string; lead: string; specialist: string };
export const OPERATOR_CODES: Record<string, string>;
export function groupAgentsByTier(agents: unknown, tasks: unknown): TierGroups;
export function hasTiers(groups: TierGroups): boolean;
export function routesToText(routes: unknown): string;
export function parseJsonList(value: string | undefined): string[];
