# Security Policy

## Supported versions

NexusAgent is under active development. Security fixes go to the `main` branch; please test against the latest commit before reporting.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub: **Security → Report a vulnerability** on this repository ([direct link](https://github.com/khangkaka066/Nexus-Agent/security/advisories/new)). Include what you found, how to reproduce it, and the impact you expect. We aim to acknowledge a report within a few days and to agree on a fix and disclosure timeline with you.

## What is in scope

Cross-tenant or cross-workspace data access, authentication and authorisation bypass, sandbox escape or network egress from a sandbox, secret or credential exposure (including in logs, errors and the UI), injection, and unsafe handling of uploaded or handed-over files.

## Good to know

- Credentials are encrypted at rest and shown masked. Failure messages shown to users are redacted of keys, tokens and server paths.
- **Local mode** (`NEXUS_LOCAL_MODE=true`) gives anyone who can reach the API an owner session. It is for a personal machine only; the default ports bind to `127.0.0.1`. Set it to `false` on any shared or public server.
- No telemetry is sent by the project.
