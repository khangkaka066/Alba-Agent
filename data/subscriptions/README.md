# Subscription logins (read-only mount)

The API container sees these folders read-only at `/var/lib/nexus/subscriptions/<name>`.
In **Settings → Subscription Plans**, a plan whose login file is found here shows a **Use detected login** button.

| Plan | Folder | File | How to create it |
|---|---|---|---|
| ChatGPT Plus / Pro / Team (Codex CLI) | `codex/` | `auth.json` | `codex login`, then copy `~/.codex/auth.json` |
| Claude Pro / Max (Claude Code) | `claude/` | `.credentials.json` | `claude login`, then copy `~/.claude/.credentials.json` (on macOS Claude Code keeps it in the Keychain: use `claude setup-token` and paste the token in the UI instead) |
| Gemini Advanced / Code Assist | `gemini/` | `oauth_creds.json` | sign in with the Gemini CLI, then copy `~/.gemini/oauth_creds.json` |
| GitHub Copilot | `github-copilot/` | `apps.json` | optional: copy `~/.config/github-copilot/apps.json`, or just use the device code sign-in |

Prefer copying only the single file. To mount a whole CLI home instead, set `NEXUS_CODEX_HOME`, `NEXUS_CLAUDE_HOME`,
`NEXUS_GEMINI_HOME` or `NEXUS_COPILOT_HOME` in `.env` (for example `NEXUS_CODEX_HOME=/Users/you/.codex`); that also
exposes the CLI's other files (history, sessions) read-only to the API container.

Files here are git-ignored. This mount holds *your* logins, so it is enabled only when
`NEXUS_MOUNTED_SUBSCRIPTIONS_ENABLED=true` (the local compose default). Leave it off on any shared, multi-tenant server.
