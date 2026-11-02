export type MountedLogin = { enabled: boolean; found: boolean; valid?: boolean; file?: string; plan?: string | null; auth_kind?: string | null; expires_at?: string | null; error?: string };
export type VerifyResult = { ok: boolean; status: string; model: string; latency_ms: number; billing_mode: string; cost_usd: string; reply: string; error: string | null };
export const BILLING_LABELS: Record<string, string>;
export function billingLabel(settings: Record<string, unknown> | undefined | null): string;
export function expiryLabel(iso: string | null | undefined, now?: number): string;
export function mountedSummary(mounted: MountedLogin | undefined | null): { tone: "off" | "none" | "bad" | "ok"; text: string };
export function nextPollSeconds(interval: number | undefined, status: string, requested?: number | null): number;
export function groupDeviceCode(code: string | undefined | null): string;
export function verifySummary(result: VerifyResult | null | undefined): { tone: "ok" | "bad"; text: string } | null;
