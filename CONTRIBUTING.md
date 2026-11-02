# Contributing to NexusAgent

Thanks for helping. Bug reports, ideas, docs and code are all welcome.

## Ways to help

- **Report a bug** or **suggest a feature** with an [issue](https://github.com/khangkaka066/Nexus-Agent/issues/new/choose). A short reproduction beats a long description.
- **Try it and tell us what was confusing.** First-run friction is the most valuable feedback.
- **Add an agent studio, template or skill.** See `packages/core-schema/templates/nexus_core_schema_templates/studios/` for the blueprints and `packages/agent-skills/catalog/` for skills.
- **Translate the interface.** Text lives in `apps/web/src/lib/messages.mjs`; a test keeps every language in step.
- **Improve the docs.** Fix anything that is wrong, unclear or out of date.

## Set up

```bash
git clone https://github.com/khangkaka066/Nexus-Agent.git && cd Nexus-Agent
cp .env.example .env            # fill the secrets as described in README.md
docker compose up -d --build    # http://localhost:3000
```

The API and `packages/` are mounted into the containers with auto-reload. The Celery worker does not reload: run `docker compose restart worker` after changing runtime code.

## Before you open a pull request

Run the same checks CI runs:

```bash
pytest && mypy packages/ apps/api/        # backend tests and strict typing
pnpm lint && pnpm check && pnpm test      # frontend
node scripts/check-npm-licenses.mjs && python scripts/check-python-licenses.py
```

Database-backed tests need `NEXUS_TEST_DATABASE_URL` and `NEXUS_TEST_APP_DATABASE_URL` (CI provides them) and are skipped otherwise.

## Project rules

- **Typing and quality.** Python 3.11+ with `mypy --strict`; TypeScript with `strict: true`. No placeholder code, mock stubs or leftover `TODO` in runtime, database or sandbox paths.
- **Tests with the change.** New behaviour comes with a test; a bug fix comes with a test that failed before the fix.
- **Isolation first.** Every table, vector payload, channel and sandbox is scoped by `tenant_id` and `workspace_id`. New tables need row-level-security policies in their migration.
- **Dependencies.** Only permissive licences (MIT, Apache-2.0, BSD, ISC and the other allowed SPDX ids in `AGENTS.md`). CI rejects anything else.
- **No telemetry.** Nothing may send usage data off the machine.
- **Plugins.** A plugin imports the kernel, `nexus_plugins.seams` and domain packages, never another plugin. See the "Plugin architecture" section of `AGENTS.md`.
- **Honest output.** Do not make an agent or the UI claim something that did not happen (a file written, a post published). If a capability is not implemented, say so.
- **Interface text** goes through `messages.mjs` in both languages.

## Pull request flow

1. Fork, create a branch, keep the change focused.
2. Describe what changed and why, and how you checked it. Screenshots help for UI changes.
3. Keep commits readable; we squash on merge when it helps.
4. Be patient and kind in review. See the [Code of Conduct](CODE_OF_CONDUCT.md).

By contributing you agree that your work is released under the project's [MIT License](LICENSE).
