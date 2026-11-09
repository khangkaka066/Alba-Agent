import { createTranslator, loadLocale } from "@/lib/i18n.mjs";

export type JsonRecord = Record<string, unknown>;

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

type LocalSession = { access_token: string; tenant_id: string; workspace_id: string; expires_in: number };

const AUTH_PREFIX = "/api/v1/auth/";
let recovery: Promise<string | null> | null = null;

/** The server's own message for a failed fetch (the browser says only "Load failed" or "Failed to fetch"). */
function unreachable(): ApiError {
  let text = "Cannot reach the server. Check that the system is running and try again.";
  try { text = createTranslator(loadLocale(window.localStorage))("error.network"); } catch { /* storage or window unavailable: keep the English text */ }
  return new ApiError(text, 0);
}

async function send(path: string, token: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, {
      ...init,
      headers: { ...(init.body instanceof FormData ? {} : { "content-type": "application/json" }), ...(token ? { authorization: `Bearer ${token}` } : {}), ...init.headers },
      cache: "no-store",
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw unreachable();
  }
}

/**
 * Local-first bootstrap: when the server runs in local mode it hands out the workspace session itself, so a missing or
 * expired token is replaced transparently. Concurrent callers share one attempt. Resolves null on a shared server.
 */
async function recoverLocalSession(): Promise<string | null> {
  if (recovery === null) {
    recovery = (async () => {
      try {
        const mode = await fetch("/api/v1/auth/local-mode", { cache: "no-store" });
        if (!mode.ok || (await mode.json() as { enabled?: boolean }).enabled !== true) return null;
        const response = await fetch("/api/v1/auth/local-session", { method: "POST", cache: "no-store" });
        if (!response.ok) return null;
        const session = await response.json() as LocalSession;
        try {
          window.localStorage.setItem("nexus_access_token", session.access_token);
          window.localStorage.setItem("nexus_tenant_id", session.tenant_id);
          window.localStorage.setItem("nexus_workspace_id", session.workspace_id);
        } catch { /* storage can be blocked: the app still receives the session through the event */ }
        window.dispatchEvent(new CustomEvent<LocalSession>("nexus:session-refreshed", { detail: session }));
        return session.access_token;
      } catch { return null; }
    })().finally(() => { recovery = null; });
  }
  return recovery;
}

export async function apiRequest<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  let response = await send(path, token, init);
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith(AUTH_PREFIX)) {
    const fresh = await recoverLocalSession();
    if (fresh) response = await send(path, fresh, init); // one transparent retry with the new session
    else if (token) window.dispatchEvent(new CustomEvent("nexus:session-expired"));
  }
  if (!response.ok) {
    const body = await response.text();
    let message = body || `Request failed (${response.status})`;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        const detail = (parsed as { detail: unknown }).detail;
        if (typeof detail === "string") message = detail;
        else if (Array.isArray(detail)) message = detail.map((item: unknown) => item && typeof item === "object" && "msg" in item ? String(item.msg) : "Invalid input").join("; ");
      }
    } catch { /* Plain text errors already have a readable message. */ }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export function tokenExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: unknown };
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch { return null; }
}

export function downloadFile(name: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000); // the download manager reads the blob asynchronously
}

export function readError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

export const starterToken = "";
