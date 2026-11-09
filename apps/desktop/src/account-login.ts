/** Fixed account actions only. Neither a renderer command nor a provider token reaches a shell. */
export const ACCOUNT_PROVIDERS = ["codex", "claude", "gemini"] as const;
export type AccountProvider = typeof ACCOUNT_PROVIDERS[number];
export const ACCOUNT_INSTALL_URLS: Record<AccountProvider, string> = {
  codex: "https://developers.openai.com/codex/cli/",
  claude: "https://code.claude.com/docs/en/setup",
  gemini: "https://antigravity.google/docs/getting-started/",
};
export function accountProvider(value: unknown): AccountProvider {
  if (typeof value !== "string" || !ACCOUNT_PROVIDERS.includes(value as AccountProvider)) throw new Error("Unknown account provider");
  return value as AccountProvider;
}
export function scopeId(value: unknown): string {
  if (typeof value !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) throw new Error("Invalid account workspace");
  return value.toLowerCase();
}
export const shellQuote = (value: string): string => "'" + value.replace(/'/g, "'\\''") + "'";
export function loginScript(args: string[]): string {
  return "#!/bin/sh\nexec " + args.map(shellQuote).join(" ") + "\n";
}
