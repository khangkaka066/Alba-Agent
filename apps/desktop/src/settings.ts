import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

export interface DesktopSettings { webUrl?: string; lastFolder?: string; recentFolders?: string[]; preventSleep?: boolean; keepInMenuBar?: boolean; notificationsEnabled?: boolean; soundEnabled?: boolean; volume?: number; downloadDirectory?: string }
export function rememberFolder(settings: DesktopSettings, folder: string | null): DesktopSettings {
  const recent = Array.isArray(settings.recentFolders) ? settings.recentFolders.filter((item): item is string => typeof item === "string") : [];
  return { ...settings, lastFolder: folder ?? undefined, recentFolders: folder ? [folder, ...recent.filter((item) => item !== folder)].slice(0, 12) : recent };
}
export function preferencePatch(value: unknown): Pick<DesktopSettings, "preventSleep" | "keepInMenuBar" | "notificationsEnabled" | "soundEnabled" | "volume"> {
  if (!value || typeof value !== "object") return {};
  const input = value as Record<string, unknown>, result: ReturnType<typeof preferencePatch> = {};
  for (const key of ["preventSleep", "keepInMenuBar", "notificationsEnabled", "soundEnabled"] as const) if (typeof input[key] === "boolean") result[key] = input[key];
  if (typeof input.volume === "number" && Number.isFinite(input.volume)) result.volume = Math.max(0, Math.min(1, input.volume));
  return result;
}
const DEFAULT_URL = "http://localhost:3000";

/** The server the window connects to: a local Docker stack by default, or any HTTPS server you point it at. */
export function resolveWebUrl(environment: string | undefined, saved: string | undefined): string {
  for (const candidate of [environment, saved, DEFAULT_URL]) {
    if (!candidate) continue;
    try {
      const url = new URL(candidate);
      const local = ["localhost", "127.0.0.1", "[::1]", "host.docker.internal"].includes(url.hostname);
      if (url.protocol === "https:" || (url.protocol === "http:" && local)) return url.origin;
    } catch { /* try the next candidate */ }
  }
  return DEFAULT_URL;
}

export function loadSettings(directory: string): DesktopSettings {
  try { return JSON.parse(readFileSync(join(directory, "settings.json"), "utf8")) as DesktopSettings; } catch { return {}; }
}

export function saveSettings(directory: string, settings: DesktopSettings): void {
  try { const file = join(directory, "settings.json"); mkdirSync(dirname(file), { recursive: true }); writeFileSync(file, JSON.stringify(settings, null, 2)); } catch { /* the app still works without persisted settings */ }
}
