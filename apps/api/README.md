# API control plane

The FastAPI app is `app.main:app`. It expects a non-owner `nexus_runtime` database connection and the shared monorepo package roots on `PYTHONPATH`. Run migrations separately with the owner connection using `alembic -c apps/api/alembic.ini upgrade head`.

## Authentication

`POST /api/v1/auth/signup` provisions a tenant, workspace, and owner without a setup token. Signup is enabled by default and can be disabled with `NEXUS_PUBLIC_SIGNUP_ENABLED=false`. It requires the separate setup database URL, rejects an email already used by another account, limits signup attempts per email, and starts with zero managed model credit. `POST /api/v1/auth/login` accepts email and password and returns workspace IDs with a 15 minute access token. `POST /api/v1/auth/register` remains a token-gated, one-time bootstrap route for private installations; `POST /api/v1/auth/token` remains available for scope-specific sign-in. Tokens require `NEXUS_SECRET_KEY` and carry tenant/workspace/user IDs; every request reloads the workspace role from PostgreSQL. Passwords use PBKDF2-HMAC-SHA256 with 600,000 iterations. Public deployments should add email verification and bot protection before exposing signup to the internet.

Service keys are created by an owner or admin at `POST /api/v1/auth/keys`, returned once, and stored only as an HMAC. Send the key in `X-Nexus-API-Key` with `X-Nexus-Tenant-ID` and `X-Nexus-Workspace-ID`. Roles are still checked against membership; key scopes further limit read, write, run, approval, and admin capabilities. Revoke keys at `DELETE /api/v1/auth/keys/{id}`.

## REST routes

- `/api/v1/workflows`: list/create/update/delete, graph validation, JSON/YAML import and export. Workflow definitions with run history are immutable.
- `/api/v1/workflows/{id}/runs`, `/api/v1/runs/{id}`, `/api/v1/runs/{id}/stream`: queue an execution, inspect its status, and stream scoped Redis events as SSE.
- `/api/v1/bots` and `/api/v1/routines`: manage bots, persistent chat turns, short lived voice tokens, Markdown schedules, and routine runs.
- `/api/v1/bots/{id}/voice/stream`: authenticated WebSocket accepting MediaRecorder WebM turns, transcribing through the configured OpenAI-compatible speech endpoint, running the persistent bot turn, and streaming TTS when configured. Without TTS credentials the browser uses local SpeechSynthesis.
- `/api/v1/approvals/{id}/resolve`: role checked decision, immutable audit record, and checkpoint resume.
- `/api/v1/sandboxes`: create/list/stop tenant scoped computers, transfer files, execute/stream terminal commands, browser actions, and screen frames.
- `/api/v1/knowledge-bases`: create/delete bases, upload a document as the raw request body with a `filename` query parameter, list documents, and test retrieval.
- `/api/v1/analytics/usage`: tenant/workspace spend, token, latency, and sandbox compute aggregates.

## Workers and runtime configuration

The API image applies migrations before starting the FastAPI server. Compose starts a separate Celery worker with Beat for scheduled routines. For local development, run the worker and scheduler manually:

```bash
celery -A app.workers.jobs:celery_app worker --loglevel=INFO
celery -A app.workers.jobs:celery_app beat --loglevel=INFO
```

The worker reads `NEXUS_REDIS_HOST` / `NEXUS_REDIS_PASSWORD`, `NEXUS_DB_*`, `NEXUS_CREDENTIAL_ENCRYPTION_KEY_BASE64`, `NEXUS_MODEL_RATES_JSON`, `NEXUS_OUTPUT_SCHEMAS_JSON`, and `NEXUS_COMPUTER_ROOT`. Add output schema models as a JSON map from model name to field/type map. `NEXUS_MODEL_RATES_JSON` is optional: a model without a price, and every subscription-plan credential, runs at `cost_usd = 0` with `billing_mode = SUBSCRIPTION_INCLUDED`. Sandbox model calls also require `NEXUS_GEN_API_KEY` (or a workspace credential) and an optional OpenAI-compatible `NEXUS_GEN_API_BASE`.

Routine scheduling registers only tenant-scoped Redis keys. The beat task reads each registered workspace and then uses `scoped_session` and forced PostgreSQL RLS for routine queries. A single Beat process should run for each deployment.

The API and worker images include the control plane and monorepo Python packages. The API and worker need access to the local Docker socket and the same host-shared `NEXUS_COMPUTER_ROOT`; set `NEXUS_DOCKER_GID` to the socket's group ID on Linux. The sandbox-supervisor image supplies the isolated Python execution image used for child containers. Screen streaming exposes frames supplied by the configured browser driver; this stack does not include a graphical desktop/browser driver. `THIRD_PARTY_NOTICES.md` and `scripts/check-npm-licenses.mjs` record and check frontend dependency licenses.
