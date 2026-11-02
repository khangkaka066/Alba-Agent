// Pure helpers for the Subscription Plans page, kept free of React so they can be unit tested.

export const BILLING_LABELS = { SUBSCRIPTION_INCLUDED: "Included in your plan · $0 per token", METERED: "Metered per token" };

export function billingLabel(settings) {
  return BILLING_LABELS[settings?.billing_mode] ?? BILLING_LABELS.METERED;
}

/** "expires in 3 days" / "expired" / "" when the login has no expiry. */
export function expiryLabel(iso, now = Date.now()) {
  if (!iso) return "";
  const remaining = new Date(iso).getTime() - now;
  if (Number.isNaN(remaining)) return "";
  if (remaining <= 0) return "expired";
  const minutes = Math.floor(remaining / 60000);
  if (minutes < 60) return `expires in ${Math.max(minutes, 1)} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `expires in ${hours} h`;
  return `expires in ${Math.floor(hours / 24)} days`;
}

/** What a connector card says about the login found in the read-only mount. */
export function mountedSummary(mounted) {
  if (!mounted?.enabled) return { tone: "off", text: "Mounted logins are disabled on this server." };
  if (!mounted.found) return { tone: "none", text: "No login mounted. Copy it into data/subscriptions/ or paste it below." };
  if (!mounted.valid) return { tone: "bad", text: mounted.error ?? "The mounted file could not be read." };
  const parts = [mounted.plan ? `${mounted.plan} plan` : "login", expiryLabel(mounted.expires_at)].filter(Boolean);
  return { tone: "ok", text: `Detected ${parts.join(" · ")}` };
}

/** Seconds to wait before the next device-login poll; GitHub asks clients to back off on slow_down. */
export function nextPollSeconds(interval, status, requested) {
  const base = Math.max(1, Number(interval) || 5);
  return status === "slow_down" ? Math.max(base + 5, Number(requested) || 0) : base;
}

/** The 8-character GitHub code is shown as XXXX-XXXX so it is easy to read out loud. */
export function groupDeviceCode(code) {
  const clean = String(code ?? "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  return clean.length === 8 ? `${clean.slice(0, 4)}-${clean.slice(4)}` : String(code ?? "");
}

export function verifySummary(result) {
  if (!result) return null;
  if (!result.ok) return { tone: "bad", text: result.error ?? "The test call failed." };
  const billing = result.billing_mode === "SUBSCRIPTION_INCLUDED" ? "included in plan" : `cost $${result.cost_usd}`;
  return { tone: "ok", text: `${result.model} answered in ${result.latency_ms} ms · ${billing}` };
}
