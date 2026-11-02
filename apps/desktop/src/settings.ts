import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

export interface DesktopSettings { webUrl?: string; lastFolder?: string }
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
