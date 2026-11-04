# Phase 17 — 3-Tier Hierarchical Studio Architecture

## Findings that shape the design
- The architect emits a flat chain; `CrewNodeSpec.process="hierarchical"` fails at runtime because no manager is configured.
- Fan-in uses `or_`, so a convergence node runs after the *first* parent, not all parents.
- Graph validators reject every cycle, so a quality gate cannot loop back to a department.
- Crew kickoff passes `node_outputs` that contain tuples (sandbox `artifacts`), which the crew input interpolator rejects:
  this is the "Unsupported type tuple in inputs" failure seen in "Generate & Run Now".
- Two sandbox nodes in one run collide on `attempt_1.py` ("Sandbox attempt number has already been used").
- The canvas round-trip (`makeSpec`) renumbers task IDs but keeps `context_task_ids`, forces `process="sequential"`,
  rewrites agent IDs and drops router names/default routes: generated multi-task crews fail to save.
- Run artifacts are flat files; artifact contracts need safe nested paths (`design/gdd.md`).

## Plan
- [x] Schema: `AgentSpec.tier`, `TaskSpec/Crew/Sandbox.expected_artifact_paths`, `CrewNodeSpec.manager_agent_id`,
      `join` (`any`/`all`), `requires_visual_evidence`, router `artifact_gate` + `max_loop_iterations`,
      `WorkflowEdgeSpec.loop_back`, `WorkflowSpec.modes` (`rigor`, `path_rules`); cycles only through loop-back edges.
- [x] Safe nested artifact paths (`artifact_file`, `list_artifacts`, download routes).
- [x] `packages/agent-runtime/hooks/validator.py`: `LifecycleHookEngine`, `ArtifactContractHook`,
      `PathScopedRuleInjector`, `VisualEvidenceHook`.
- [x] Crew builder: hierarchical crews run their Department Lead as `manager_agent`.
- [x] Compiler: JSON-safe crew inputs, `and_` joins, hook execution, path rules, quality-gate loop-back reruns.
- [x] Sandbox: per-invocation script names; export declared files into the run artifact directory.
- [x] Studio blueprints (game 49, video 26, software 32 agents) in `templates/studios/`, listed in the gallery.
- [x] Meta-Architect rigor modes (`minimal`, `standard`, `full_studio`) with layered DAG layout.
- [x] API: `rigor` on generate/refine requests.
- [x] Web: rigor selector, tier-grouped crew cards with specialist drawer, lossless spec round-trip, loop-back edges.
- [x] Regenerate JSON schemas; tests; pytest, mypy, pnpm lint/check/test, branding grep.

## Review
- pytest: 80 passed, 11 skipped (need Postgres/Redis; same 11 as before). New file: `apps/api/tests/test_phase17_studio.py` (32 tests).
- mypy --strict: 2 errors, both pre-existing (`registry.py:403`, `test_phase16_media_tools.py:34`); none introduced.
- web: `tsc --noEmit`, `eslint --max-warnings=0`, `node --test` (6 tests) all clean.
- Live check: instantiated the 49-agent game studio from the gallery, opened it in the Studio UI, pressed Save: the stored spec was identical
  (agents, tiers, manager, task ids/contexts/paths, router routes, loop-back edges, modes). 13 nodes, 15 tier groups, no page errors.
- Branding grep returns nothing.
- NOT verified: a real model-backed run of a studio (cost; needs explicit go-ahead), `scripts/smoke_test.py` (needs provider keys).


---

# Phase 18 — Autonomous Team Topology Evolution (`packages/agent-runtime/team_evolution`)

## Design decisions
- Versions are immutable `Workflow` rows (name + version); a **generation** is a `workflow_topology_versions` row that points at one.
  A proposal stores its spec inside the generation row and only becomes a `Workflow` when approved, so the workflow list is never polluted.
- Mutations operate on the spec as a plain document and are validated three ways: pydantic, `FlowCompiler.validate`, and (in tests) `compile()`.
- Fitness = 0.45 completeness + 0.35 quality/human + 0.20 efficiency. Efficiency is measured against the lineage's first generation
  (v1 scores 1.0 by definition), so a generation that costs 2x scores 0.5 on that term.
- Rollback rule: child fitness < parent fitness - 0.05, evaluated after each finished run (including runs that finish after an approval).
- Dynamic spawning is offered to Tier-1 directors. A CrewAI `manager_agent` may not hold tools, so managed Tier-2 leads cannot receive it;
  leads in unmanaged crews can.

## Verification
- pytest: 100 passed, 12 skipped locally; with Postgres: `test_phase18_generations_db.py` passes against the real runtime role with RLS
  (proposal -> approval -> autonomous rollback -> no repeat of a rolled-back change -> tenant isolation).
- mypy --strict: only the 2 pre-existing errors.
- web: tsc, eslint, `node --test` (11) clean.
- Live UI: proposal card, version selector, graph diff (2 new / 2 changed / 1 pruned), run disabled while previewing, approve, roll back.
- NOT verified: a model-backed run of an evolved team, and the FULLY_AUTONOMOUS loop on real runs (only on seeded run data).


---

# Phase 19 — Subscription Plan Connector Hub + Compose packaging

## Findings that shape the design
- `NEXUS_MODEL_RATES_JSON` is already optional at startup (defaults to `{}` + built-in rates), but three call sites still *raise* when a model has no rate:
  `LiteLLMRouter.complete`, `LiteLLMEmbeddingRouter.embed`, `AppServices.usage_handler`; `architect._approved_chat_models` and `scripts/smoke_test.py` also gate on rates.
- Credentials are resolved as `(api_key, base_url)` tuples by `SqlGatewayStore`; subscription credentials need more (billing mode, extra headers, a Copilot token that must be re-minted every ~30 min, an OpenAI-format wire for Copilot-served Claude/Gemini models).
- The compose stack is already running with real data (named volumes `nexus_postgres_data`, `nexus_artifacts`, ...). Renaming volumes or switching postgres to alpine (musl collations) would orphan or corrupt it, so volume/image names stay.
- Images are built into `/workspace` (not `/app`); dev bind mounts target `/workspace/apps/api` and `/workspace/packages`.

## Plan
- [x] `model_gateway/subscription_connectors.py`: connector catalog, Codex/Claude/Gemini/Copilot credential parsers (JWT expiry), Copilot device flow + session-token broker.
- [x] Billing: `ResolvedCredential`, `UsageRecord.billing_mode`; unknown rate or subscription credential => `cost=0`, `SUBSCRIPTION_INCLUDED`; chat + embedding routers; `usage_handler`; architect/evolution model approval no longer needs a rate.
- [x] Migration 0015: `token_usage_logs.billing_mode`.
- [x] Presets: category `subscription` (OpenAI/Codex, Claude, Gemini, GitHub Copilot) + gateway templates (ShopAIKey, OpenRouter, CLIProxyAPI bridge).
- [x] API `routers/subscriptions.py`: connectors + mounted-credential detection, import (mounted/paste), Copilot device start/poll, verify (real 1-token call through the runtime resolution path).
- [x] Web: "Subscription Plans & AI Providers" page with the two-mode switch, device-code UI, detect/import, "Verify Subscription & Test Model".
- [x] Compose: bind-mounted `./data/artifacts`, optional read-only subscription mounts, dev `--reload` source mounts, sandbox image with ffmpeg/pillow/headless browser; `.env.example`, `.gitignore`, README.
- [x] Tests (pytest, node), mypy, lint/check, branding grep; `docker compose up -d --build`; smoke test; a real workflow run writing into `./data/artifacts`.

## Review (Phase 19)
- pytest: 113 passed, 13 skipped locally; with Postgres and the runtime role all DB-backed tests pass, including the new `test_phase19_credentials_db.py`
  (RLS, per-provider defaults, Copilot session minting, `billing_mode` persisted). Fixed a stale Phase 18 assertion (RLS table count 30 -> 32).
- mypy --strict: only the 2 pre-existing errors. web: tsc, eslint, `node --test` (16) clean. Branding grep: 0.
- Live stack (`docker compose up -d --build`, migration 0015 applied): all 7 services healthy; `scripts/smoke_test.py` passed against the real model with
  no rate table (cost $0.001). A real run with `gpt-4.1` (not in the rate table) completed, wrote `deliverables/summary.md` into `./data/artifacts/<tenant>/<ws>/<run>/`,
  streamed events over SSE and logged `SUBSCRIPTION_INCLUDED` at $0.
- Live UI (Playwright): two-mode switch, four plan cards, paste modal error path, real GitHub device code shown, verify button against a stand-in bridge.
- NOT verified: any real ChatGPT/Claude/Gemini/Copilot account (no credentials here). Only GitHub's device-code request was made for real (code shown, never approved).
  Codex/Claude/Gemini wire formats rest on public knowledge of those tokens; the verify button reports the true provider error.
- Deviations from the spec: kept existing images/volume names (alpine postgres and renamed volumes would break the live data); mounts target `/workspace` (not `/app`);
  mounted logins are opt-in via `NEXUS_MOUNTED_SUBSCRIPTIONS_ENABLED` (they belong to the operator, not tenants).


---

# Phase 20 — Cursor-style workspace (`apps/web`) and Electron desktop (`apps/desktop`)

## Findings that shape the design
- `POST /api/v1/architect/generate-workflow` with `auto_run: true` already generates the team, persists the workflow and queues the run in one call; the composer needs no new pipeline endpoint, only an optional `input_files` pass-through (desktop folder files).
- Sandbox input files must be flat file names (the supervisor rejects paths), so a mounted folder reaches agents as flat copies plus a `workspace_manifest.json` that maps flat name -> real relative path; accepting an artifact writes it back to the mapped path.
- `workflow-studio.tsx` already opens any workflow through `openWorkflowId`; the canvas only needs its hard-coded `initialNodes/initialEdges` removed and an `embedded` mode (composer owns prompting and running).
- `LiveInspector` is mounted at app level and owns the SSE stream; the workspace needs the same stream for the composer, terminal and explorer, so the stream becomes one shared hook.
- Sandbox containers are networkless; the browser-in-sandbox is local-only. The desktop app is an Electron shell around the web app (AGENTS.md: "Electron shell connecting to local Docker stack or remote HTTPS server").

## Plan
- [x] Backend: `input_files` on generate-workflow (flat names, 1 MiB cap, merged into run input) + test.
- [x] `NexusOctopusLogo` SVG + `icon.svg`; used in sidebar, favicon, desktop icon. Remove "Studio" from the sidebar brand (done).
- [x] `lib/workspace.mjs`: artifact classification, file tree, line diff + split rows, run-event reducer, team summary (+ node tests).
- [x] Workspace UI: explorer (sidebar), workbench (diff / media / terminal / screen), composer (team pill, live actions, file chips, approvals), canvas view toggle (⌘\), no dummy nodes.
- [x] `/quickbar` route for the desktop mini-bar.
- [x] `apps/desktop`: Electron main/preload, folder mount IPC with path guards, global shortcut, notifications, electron-builder (dmg/exe/AppImage), icon, tests.
- [x] Verify: pytest/mypy, web lint/check/test, desktop tsc + tests + electron-builder, real run from one composer prompt, Electron launched and driven over CDP.

## Review (Phase 20)
- Web: tsc, eslint, `node --test` (30) clean. New: `lib/workspace.mjs` (tree, line diff, run-event reducer, team summary, folder flattening; 7 tests), shortcut `toggle-canvas` (⌘/Ctrl+\).
- Backend: pytest 116 passed (13 skipped without services), mypy only the 2 pre-existing errors. Fixes found by running the real pipeline from one prompt:
  1. skill `deep-web-research-and-fact-checking` named tools `scraper`/`rag` that do not exist (real IDs `web_scraper`/`knowledge_rag`): any run binding it failed at crew build. Added a test that every seed skill only requires existing tools.
  2. a sandbox node with no declared deliverables exported nothing; undeclared files the sandbox wrote are now exported (inputs left unchanged and the manifest are skipped).
  3. the sandbox quota guard reserved `timeout x max_rounds` (a whole FREE month) per node, so a second sandbox node got HTTP 402; it now reserves one attempt.
- Desktop: `apps/desktop` Electron app (frameless, folder mount with path/symlink/secret guards, global Quick Task shortcut, notifications, electron-builder). 5 tests; licence check passes (213 packages); a real 94 MB `.dmg` builds. Driven over CDP against the live stack: bridge present with no Node access, folder tree shown, one prompt -> team -> `service.py ~ Modified` mapped to `src/auth/service.py` -> diff -> Accept wrote the real file.
- NOT verified: the OS-level global shortcut press and OS notification banners (cannot be simulated headless; registration printed no conflict warning), `.exe`/`.AppImage` builds (need Windows/Linux), signing/notarization, and the 3-tier `full_studio` team in this UI (only `minimal` runs were exercised end to end).
- Design notes: the sandbox accepts only flat file names, so a mounted folder reaches agents as flat copies + `workspace_manifest.json`; "Accept" writes artifacts back to the mapped real path. Agents never touch the real folder directly.


---

# Phase 21 — Zero-auth local workspace, unified Studio, locked 3-item navigation

## Findings that shape the design
- Every "Not connected / Sign in" message comes from one place: the web app has no token until the user signs in. The cure is a local session minted by the API, not per-screen special cases.
- A token-less owner session is only safe on a single-user machine. It is gated by `NEXUS_LOCAL_MODE` (default off in code, on in the local `docker-compose.yml`, absent from the production compose) and the local compose binds API and web to 127.0.0.1.
- `generate-workflow` with `auto_run` already does design + persist + run, so the unified Studio is a front-end change; artifacts for a Files gallery come from the existing `/api/v1/runs` listing.
- Persistent-bot (`teammates`) and Intelligence screens stay in the code base (AGENTS.md lists them) but leave the main navigation; they are reachable from Settings → expert mode.

## Plan
- [x] API: local workspace seed (tenant/workspace/owner/budget, plan ENTERPRISE), `POST /auth/local-session`, `GET /auth/local-mode`, startup seed; `GET /settings/ai-status`; channel presets (TikTok, Facebook, YouTube). Tests.
- [x] Web shell: auto session (refresh before expiry), left rail = 3 items + Settings, header with AI status pill and `?` help (shortcuts modal), no workspace widgets.
- [x] Unified Studio: idle (centered composer + starter chips + recent tasks) -> active (360px conversation + main stage with file tabs, collapsible terminal, canvas toggle); pending-optimisation banner.
- [x] Files gallery, Tools & Channels page, Settings in three sections + expert mode (telemetry, bots, all providers).
- [x] Verify: lint/check/tests/pytest/mypy, rebuild stack, browser at localhost:3000 with empty storage.

## Review (Phase 21)
- API: `POST /auth/local-session` + `GET /auth/local-mode` (only when `NEXUS_LOCAL_MODE=true`), the local tenant/workspace/owner/credit are seeded at startup and on first call (idempotent, plan ENTERPRISE); `GET /settings/ai-status`; `DELETE /settings/credentials/{id}`; TikTok/Facebook/YouTube presets. pytest 119 passed (15 skipped without services), mypy only the 2 pre-existing errors; the DB-backed local-mode and AI-status tests pass against PostgreSQL with the runtime role.
- Web: tsc, eslint, `node --test` (30) clean. Verified in a fresh browser profile at http://localhost:3000: no "Not connected / Sign in" text, rail = Làm việc / Sản phẩm & File / Công cụ & Kênh + Cài đặt AI, no workspace widgets, idle shows only the centred composer with three starter chips (no terminal, no Deliverables box, no right column); after a real prompt the layout becomes 360px chat + stage with file tabs, collapsed terminal and the canvas toggle; Files gallery + preview, Tools channels, Settings in three sections, expert mode links, `?` shortcut modal.
- Desktop re-driven over CDP with the new layout: folder chip on the home screen, one prompt, `service.py` file tab, "Chấp nhận vào proj" wrote the real file.
- Reliability fixes found by running it: the Meta-Architect now retries an unparseable JSON reply (it failed whole requests with a 422), `max_output_tokens` raised to 8000; the DELETE route needed `response_class=Response`.
- NOT done / honest limits: the social channel cards only store an encrypted token and run a connectivity check (endpoints from public docs, never exercised with a real account); no agent tool publishes to TikTok/Facebook/YouTube yet. The "agent tự tối ưu kỹ năng" banner appears when pending self-healing proposals or distillation recommendations exist; it links to the expert page and does not apply anything by itself. Settings → plan cards keep their English button labels. A model-written program can still fail verification (one of three desktop runs ended "thất bại" for that reason).

## Interface language (Vietnamese + English)
- [x] `lib/messages.mjs` (vi/en tables), `lib/i18n.mjs` (translator, storage, status/date helpers), `LocaleProvider` + `useLocale()`, VI/EN toggle in the header.
- [x] Every Vietnamese string in studio shell, Work, Files, Tools, Settings, shortcuts and run progress moved to keys; pure helpers take an optional `t`.
- [x] `test/i18n.test.mjs`: tables have identical keys and placeholders, every key used in `src/` exists, run text follows the language.
- Review: lint + `tsc` clean, 38 `node --test` pass; browser check shows no Vietnamese text left on Work/Files/Tools/Settings/help/palette in English, choice persists after reload.
- Not translated: text that was already English (canvas, provider modal fields, teammates/intelligence panels) and text that comes from the server (workflow names, run errors, chat messages already written).

## Phase 22 — "Everything is a plugin" runtime kernel
Scope approved by the user: kernel, boot through the container, sandbox / tools / memory / llm plugins, docs and boundary tests. Not in scope: splitting `flows/compiler.py` into node-handler plugins, a third (native) agent loop, PTC, a host-terminal sandbox, per-workspace plugin config in the database, cross-process reload broadcast.
- [x] `nexus_kernel` (name chosen over `core/`: a top-level `core` module would collide with other imports): `Context` (scoped services, typed keys, reversible effects, 5 event modes), `Plugin` lifecycle (pending → active → disposed, dependency-driven start/stop), YAML rows + patches + dump, `Kernel.boot/reconfigure/close`.
- [x] `nexus_plugins`: `seams` (service keys), `infrastructure` (db/redis/qdrant), `sandbox` (+ docker provider plugin), `llm`, `memory` (checkpoints + event emitter), `tools`, `sandbox_runner`; default `plugins.yaml`.
- [x] `create_default_services` boots through the kernel; `AppServices` keeps its public surface; API and worker shut down by closing the kernel.
- [x] Tests: mount/unmount, dependency waiting and cascade, no leaked listeners/services/prompt sections, config patches, reconfigure diff, import-boundary scan, boot of the real plugin list.
- [x] AGENTS.md + `packages/agent-runtime/README.md`.
- Verify: pytest, `mypy packages/ apps/api/`, smoke test, branding grep, docker rebuild + a real run.
- Review: pytest 152 passed / 6 skipped against Postgres with the runtime role (was 134 without DB before this phase's tests were added: 14 kernel + 9 plugin tests are new); mypy only the same 2 pre-existing errors; branding grep clean in source (hits only inside ignored build output); `python -m nexus_plugins dump-config` works; API and worker boot through the kernel; a real workflow (sandbox node, gpt-4.1) completed end to end and wrote its artifact, usage and events.
- Moved out of `services.py` (-190 lines): rate/credential/model-client helpers (`support/llm_service.py`), tool registries (`support/tool_service.py`), sandbox/runner/connection wiring (plugins). `AppServices` keeps its public surface; `create_default_services` is now `async`; `AppServices.shutdown()` closes the kernel.
- Found while testing: the model provider behind `NEXUS_OPENAI_API_BASE` (api.shopaikey.com) intermittently never answers `gpt-4.1` requests (4 of 6 parallel direct calls timed out at 60 s, `gpt-4.1-mini` was fine). Runs that hit it sit in `running` until the client's 600 s timeout, and with `--concurrency=2` two such runs block the queue. Unrelated to the plugin work; worth a per-request timeout and a run-level deadline.
- Not done (by agreement): compiler node handlers as plugins, learning-transfer capsule injection as a plugin, cross-process reload of the plugin list, per-workspace plugin config in the database.

## Phase 23 — Feature film studio, and social channels only for teams that publish
- [x] `feature-film-production-studio` blueprint (50 agents: 3 directors, 7 departments, 2 sandbox teams, QA with continuity and rating audit, distribution team); domain `film`; weighted detection so "bộ phim ngắn…/make a film" builds it while "documentary video…" stays the video studio.
- [x] `WorkflowModesSpec.channels` (default `()`, so saved specs stay valid); the film studio declares TikTok, Facebook, YouTube; JSON schemas regenerated.
- [x] Tools page: the Social channels section appears only when a workspace team declares channels (or a channel is already connected, so it stays manageable); chat shows a one-line hint with a link to Tools until the declared channels are connected.
- Review: pytest 150 passed / 15 skipped locally, mypy only the 2 old errors, web lint/check and 42 `node --test` pass. Real Meta-Architect run on a Vietnamese prompt returned the film studio, 50 agents, channels set. Browser: Tools shows no channels in a fresh workspace, shows the three cards after the film team exists (and in English), the hint appears in the chat and opens Tools.
- Not verified: a full 50-agent film run (cost). Not built: posting to the platforms. The release team writes publish-ready packages per channel and stops at sign-off; the connect cards still only store a token and check connectivity.

## Phase 24 — Model selector and a simpler navigation
- [x] `GET /api/v1/settings/chat-models`: chat models the workspace can run (connected credentials, local models, and platform keys with budget), named `provider/model` exactly as the Meta-Architect's `preferred_model` expects; a model it would reject is never listed. DB test added.
- [x] Model selector: header dropdown (replaces the static "AI ready" pill) and a compact pill in the home prompt and the chat bar. The choice is remembered per browser and sent as `preferred_model`, which sets the team's agent and director models.
- [x] Rail = Work + Settings. `/files` redirects to Work; `/tools` and `/capabilities` redirect to Settings → Integrations (channels still gated by the film team, MCP and skills; uploaded documents only in expert mode). Shortcut `nav-integrations` (Mod+2) replaces nav-files/nav-tools.
- [x] Work view: download button on every file, a download button on each chat chip, a workspace file tree in the sidebar (this task first, then earlier tasks) that opens a file in Work from any page. Video and audio already play inline; verified with a generated WAV.
- Review: pytest 160 passed / 6 skipped with Postgres, mypy only the 2 old errors, web lint/check and 46 `node --test` pass. Browser: picker lists models and switches, the pick reaches the request body and survives a reload, English mode has no Vietnamese text left on Work/Settings/Integrations, redirects work.
- Not verified: an inline video file (no mp4 in the workspace; the video branch is the same component as audio). Switching models is per browser, not stored on the server.

## Phase 25 — Audit fixes: session recovery, `/run` alias, model picker, green CI
- [x] CI: the red "Python tests and type checks" step was only mypy (pytest passed in CI: 154 passed). Two errors fixed for real instead of "pre-existing": the unused `type: ignore` in `registry.py` and an `Any` return in `test_phase16_media_tools.py`. mypy now reports 0 errors. Actions moved off Node 20 to the latest majors (checkout v7, setup-python v7, setup-node v7, pnpm/action-setup v6, docker/* v4/v7); every input the workflow passes still exists in those versions. Ran the other CI steps locally too (npm and Python licence checks, branding grep, frozen lockfile).
- [x] API client: a 401 now triggers the local-session bootstrap and one transparent retry (shared across concurrent callers); a failed fetch says "cannot reach the server" instead of the browser's "Load failed". The sidebar tree waits for the token and treats each list as optional.
- [x] CORS: `allow_credentials=True` with the explicit origin list; local mode additionally accepts any `http://localhost|127.0.0.1[:port]` origin (desktop picks a free port). A shared deployment gets no pattern. Preflight tests cover allowed and rejected origins.
- [x] `POST /api/v1/workflows/{id}/run` is an alias of `/runs`.
- [x] Model picker always opens: connected models, well-known models (marked "needs a key" until their provider is connected) and a "custom model id" box; the same menu in the header and in the prompt bars, placed where there is room. A typed id is accepted by the Meta-Architect when a provider that can serve it is connected (verified: `openai/gpt-4.1` builds a team on that model; `anthropic/...` without a key is refused with a clear message).
- Review: pytest 162 passed / 6 skipped with Postgres (152 / 16 without), mypy 0 errors, web lint/check/48 tests pass; browser checks of the 401 retry, the unreachable-server message and the picker.
- Deviations: the DeepSeek suggestion is `deepseek/deepseek-chat` (the id the provider preset knows), not `deepseek-v3-1`; type `deepseek/deepseek-v3-1` in the custom box to use it. CI itself can only be confirmed by pushing.

## Phase 26 — Task history, failure diagnostics and cross-team handoff (workspace switcher excluded by the user)
Decisions taken where the user did not answer: attaching the previous run's files is the default for a follow-up (shown as removable chips); deleting a task removes its conversation, run, checkpoints and output files (confirmed in the UI), never the audit log; handoff copies files into the new run, so deleting the source later breaks nothing.
**Pha 1 — history and failures**
- [x] Migration `0016`: `task_conversations`, `conversation_messages` (RLS, scoped FKs), `workflow_runs.failure` JSONB, backfill of existing runs.
- [x] API: conversations list/get/append-note/delete; runs expose `conversation_id` and `failure`; `generate-workflow` writes the user prompt and team card to a conversation; `POST /runs/{id}/retry` (`step` resumes from the last good checkpoint, `team` starts a new run).
- [x] Runtime: the failing node, agent (when known), error type, sanitised message and short traceback are saved on the run.
- [x] UI: sidebar lists every task with a status dot and its files; opening a task restores its whole thread; failure card with details + retry buttons; delete with confirmation.
**Pha 2 — handoff foundation**
- [x] `input_artifacts` on `generate-workflow`: server validates run/file in the same workspace, copies files into the new run, records `upstream_artifacts` (name, size, mime, excerpt); the Meta-Architect is told what exists; sandbox nodes receive the files.
- [x] `GET /artifacts/search` for the picker. UI: follow-ups attach the previous run's files by default (chips), `@` picker and attach pill in the prompt bar.
**Pha 3 — next teams**
- [x] Marketing & Social Publishing blueprint and Analytics & Optimization blueprint; `studio_id` to force one; handoff buttons on completed task cards.
- Review: pytest 178 passed / 6 skipped with Postgres (166 / 18 without), mypy 0 errors, web lint/check/51 tests, licence and branding checks pass. Browser: the sidebar lists every task with a status dot, reopening a failed task after a reload restores its thread and failure card, retry-step resumes the same run, delete asks first and removes the task; the hand-off buttons send `studio_id` + `input_artifacts` + the thread id; `@` opens the picker; removing a chip works. Live: a new team started from `squares.md` used its content; the architect builds the requested studio (19 agents at standard rigor) and refuses `../` paths and runs of other workspaces.
- Notes: a retried step re-runs the node that failed from its start (finished departments are skipped); the failing agent is recorded only when the code path knows it, so most failures name the department, not an agent; large files (video) are described to the sandbox but not uploaded because its input limit is 1 MiB; posting to TikTok/Facebook/YouTube is still not implemented: the marketing team prepares packages and a checklist. Observed while testing: a minimal team's crew can claim an exported file it never wrote (the live handoff run reported `summary_of_squares.md` but no file existed) - a separate reliability issue.

### Phase 26 follow-up — name the failing agent, and make file claims true
- Agent: `crews/tracking.py` wraps `execute_task` on the built crew's agents (manager included, instance level, nothing global) so the run record names the agent that raised (or the last one that started when the failure came after the crew finished); sandbox nodes report "Coder + Reviewer". Verified live: a team with a model the provider does not have fails with `failed_agent_name = "Note Writer"`. Found while verifying: the worker does not hot-reload, so it must be restarted after runtime code changes.
- Claims: `hooks/claims.py` finds file names a team reports (`exported_filename`, `files_written`, ...) and the files a task description tells the agent to write ("to a file named x.md", not "parse x.md"). The generator declares those as the task's `expected_artifact_paths`; at run time claimed files join the artifact contract: a document the agent never wrote is rebuilt from the team's own text and the recovery is recorded, a video or other media is never invented. In a workflow without an artifact gate an unmet contract now fails the node ("did not deliver what it reported: x (missing)"); with a gate the existing rework loop still decides. Verified live: the earlier "summarise squares.md" request now ends with a real `summary_of_squares.md`.
- Review: pytest 184 passed with Postgres, mypy 0 errors; 6 new tests including real CrewAI agents.

## Phase 27 — README and discoverability
- README rewritten in English (`README.md`) with a Vietnamese twin (`README.vi.md`): value pitch, real screenshots and a tour GIF of the current interface, studios table, mermaid flow and architecture, quick start, model connection, honest limits. Old screenshots and the old demo GIF (previous interface) removed.
- Community files: CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CITATION.cff, issue forms, PR template. `docs/assets/social-preview.png` (1280x640) is ready to upload by hand (GitHub has no API for it).
- GitHub repo description and 20 topics set with `gh repo edit`.
- Found while making the screenshots: asking for something similar twice could fail with a 500 because the Meta-Architect picked an existing workflow name (unique per workspace and version). `free_workflow_name` now appends " (2)", " (3)"; tested.
- The screenshots come from a throw-away "Showcase" tenant (real runs, real UI); the canvas picture is a crop of a real team graph. That tenant stays in the dev database; delete it if unwanted.

---

# Phase 28 — Benchmark: NexusAgent vs Claude Code CLI and a DeepSeek harness on small coding tasks

## Decisions (from the user)
- Problem: write small functions / fix small bugs; hidden tests give an automatic verdict.
- Systems, same ShopAIKey key and base model, same prompts, same limits:
  A. NexusAgent (compact team, sandbox coder + reviewer; ShopAIKey connected through its OpenAI-compatible gateway card)
  B. Claude Code CLI (installed, 2.1.283) with ANTHROPIC_BASE_URL / auth token pointed at ShopAIKey
  C. DeepSeek Harness (`dsh`, github.com/deepseek-ai/deepseek-harness, MIT, developer preview): `dsh --profile headless --json "<task>"`
     (stdin with `-`), `--permission-mode workspace-write`, `--approval-policy never`; ShopAIKey wired through its `llm-pi-ai`
     plugin (`baseURL`, `apiKeyEnv`, model list) in a `--patch` overlay file. Run from an isolated install dir; read SAFETY.md first.

## Design
- 60 original tasks (no copying from public benchmarks, to avoid contamination): 30 "implement from spec", 30 "fix the bug".
  Each task dir: `prompt.md`, `starter/`, hidden `tests/`, `meta.json` (category, difficulty, allowed paths).
- Task validity check: reference solution passes hidden tests, untouched starter fails them.
- Grader: copy the produced workspace into a fresh Docker container (no network), run hidden tests. Verdicts: PASS / FAIL / SEVERE.
- SEVERE = edits or deletes tests, writes outside allowed paths, destructive command, claims success while hidden tests fail,
  or hangs past the limit.
- Metrics per task and system: completion (hidden tests pass), severe error, wall time, billed cost (gateway usage, not estimates),
  interventions (approval cards + permission prompts + manual retries a human would have had to answer).
- Fixed limits for every system: 1 attempt, 10 min wall clock, same token cap, same Python image.
- Report: completion with Wilson 95% CI, severe-error rate, median/p90 time, cost per task and per success, interventions per task,
  per-category split, failure taxonomy. Human review: blind rubric (1-5 correctness of approach, readability) on a 15-task sample.
- Secrets: ShopAIKey key only in an env var / untracked `.env`; never committed or logged.

## Plan
- [x] 0. Settled with the user: ShopAIKey key + model `gpt-6-luna`, cost cap 12 USD, blind review by Claude (Sonnet 5.5)
- [x] 1. Spike: start the stack, connect ShopAIKey as an OpenAI-compatible gateway, drive one run headlessly through the API
- [x] 2a. Task format, `bench.validate` (starter must fail, reference must pass, prompt must not leak hidden names), 2 example tasks
- [x] 2b. 58 more tasks authored by 4 parallel subagents (impl-002..030, fix-002..030), each validated; 60/60 valid
- [x] 3. Grader (Docker `nexus-sandbox-python:3.11`, no network, caps dropped) + SEVERE detectors (protected files, canary/outside writes); `bench.selftest` proves PASS/SEVERE/FAIL/false-claim with fake agents
- [x] 4. Adapters: claude_code, claude_code_sbx, dsh, nexus, nexus_plain all done; claude_code done (`--bare`, so the operator's CLAUDE.md/hooks do not leak in); dsh and nexus need the ShopAIKey details
- [x] 5a. Runner `bench.run` (resumable, infra errors retried then excluded, JSONL records)
- [x] 5b. Cost = real ShopAIKey account counter delta per system run (cents), no price list needed
- [x] 6. Pilot on 5 tasks x all systems; project total cost; ask the user before the full run
- [x] 7. Full run (60 tasks x 5 configurations) and report: benchmarks/code-tasks/REPORT.md

## Review

- Review (Phase 28): see `benchmarks/code-tasks/REPORT.md`. dsh 60/60, Claude Code 59/60 (57/60 with its own sandbox), NexusAgent 38/60 (41/60 with the plain prompt); 0 severe errors; real spend 6.94 USD of 12.
  Harness bugs found and fixed on the way: impl-019 test contradicted its prompt, two wrong NexusAgent API assumptions, workflow-name collisions, operator skills leaking into dsh, dsh telemetry plugin on by default, `_count()` miscount.
  Cleaned up: project `.env` restored, benchmark stack stopped (`docker compose -p nexus-bench down`, volumes kept), the ShopAIKey key lives only in untracked `benchmarks/code-tasks/.env.bench` (mode 600).
  NOT done: repeated runs per task (pass@1 only), multi-file studio-style tasks, a human other than Claude grading the blind sample.


# Phase 29: Verified-by-construction sandbox results (accuracy > speed > cost)

Motivation: Phase 28 showed NexusAgent completes 38/60 while dsh/Claude Code complete 59-60/60. Failures are in verification, not code:
every architect design verifies with `python -m compileall .`, the LLM reviewer then rejects for lack of evidence, and a failed run exports nothing.

## Decisions (settled with the user)
- Priority: accuracy and verifiability first, then speed, then cost.
- Fully automatic: no test-author agent, no human approval on the main path (`ApprovalGateNode` stays an opt-in node).
- Three honest states: `VERIFIED(level)`, `UNVERIFIED` (candidate, labelled, separate field), `FAILED`.
- A machine decides from an evidence bundle; the reviewer LLM can never promote or demote a state.
- `on_unverified` workflow policy: `deliver_labeled` (default) | `fail`.
- Levels: V1 existing tests/examples, V2 heterogeneous N-version differential agreement on algorithmically generated inputs,
  V3 coder-written tests accepted only after fail-on-baseline + AST mutation score + hash lock. `compileall` is never evidence.
- No guarantee of false-verified = 0; each level is measured separately against hidden tests and the VERIFIED threshold is set from data.

## Plan
- [x] 1. Evidence model + three states; compile-only is never evidence (validate endpoint warns instead of rejecting, so existing templates keep working)
- [x] 2. V1: staged tests run by a probe the coder cannot edit (hash-checked, nonce-guarded); machine verdict decides exit code
- [x] 3. V3 gates: fail-on-baseline, AST mutation score (stdlib `ast`), >=3 tests; `on_unverified` policy; unverified files under `unverified/`
- [ ] 4. V2: algorithmic input generation, two heterogeneous independent solvers, output agreement
- [x] 5a. `on_unverified` policy + architect draft repair loop (HTTP 422)
- [ ] 5b. Escalation ladder (stronger model on later rounds)
- [ ] 6a. Adversarial set (12 tasks, adv-A/B/C) and a measured false-verified rate per level
- [ ] 6b. Rerun the 60 tasks on the final build, update REPORT.md

## Progress notes (Phase 29)
- Pilot on the 22 tasks that failed in Phase 28 (V1 only): 16 PASS. Pilot on the remaining 6 + 2 controls (V1+V3): 7/8 PASS, the one miss was an architect HTTP 422, now repaired.
- Budget: the user raised the cap from 12 to 16 USD. Spent so far 8.40 USD (6.94 + 1.13 + 0.33).
- Deviation: no new run status `completed_unverified` (would touch DB, web and checkpoints); the label lives in `unverified_nodes` and `unverified/` files instead.
- V2 is built only if the adversarial run shows V3 verifying wrong answers.

## Review (Phase 29, benchmark and infrastructure)
- Full 60-task result after the verification rework: NexusAgent 57/60 (95.0%, Wilson 86.3-98.3%), against 38/60 before; DeepSeek Harness 60/60, Claude Code 59/60. McNemar versus both is not significant. Details in `benchmarks/code-tasks/REPORT.md`.
- Root cause of the infrastructure failures: the persistent computer supervisor created one `sleep`-forever container per run and nothing removed it. Fixed with release-at-node-end (reference counted per run), re-provisioning on the same row, an orphan reaper by label, a per-process concurrency cap and provisioning retries.
- The fix caused a regression, caught by the benchmark: `read_run_file` required a running computer, so deliverables were lost after release while the run still reported completion. Fixed (host-backed files stay readable; an unreadable reported file now fails the run). Lesson: a silent `except ... continue` around an export hides lost work.
- Still open: held-out and harder benchmark with repeats, the 3 remaining failures, no integration test for re-provision and reaper against a real database, speed (median 193 s vs 55 s), GitHub connection, OAuth login.

# Phase 32 — Adaptive team size: solo for light tasks, sequential or parallel team for heavy ones (solo + repair DONE; parallel NOT built)

## Progress notes (Phase 32)
- Calibration on 70 tasks / 241 solo-system records: static signals predict solo effort weakly (best usable one, prompt length, Spearman 0.48) and predict failure not at all (<= 0.2). So the router is only a gate for "plain code or calculation request" vs everything else; the real mechanism is run solo, verify, repair on failure.
- Built: `on_failure: continue` on sandbox nodes (compiler no longer raises, the attempt's files are evidence not a deliverable), `architect/adaptive.py` (assess, solo graph start -> solo -> gate -> repair), `rigor` = auto|solo (API default is auto; service default unchanged), `nexus_auto` benchmark system.
- Result: 10/10 on the multi-file tasks, then 11/12 on four repeats of ledger, stock and mdlite (one run each of the 10; the stock miss was a verified-but-wrong solo result, so the gate never fired). 1 repair attempt ran in real runs and rescued a solo that "did not run cleanly and had no tests". Small sample, one model; not evidence of superiority over the earlier chain.
- Not built, on purpose: the parallel team. Two engine gaps first: a sandbox node cannot see files written by an earlier node of the same run (only the original inputs and node summaries), and shipped tests are staged for every node, so a worker holding one module could never verify against the whole suite. No measurement so far shows a task here that needs a team (the heaviest solo run used 12.9k output tokens).
- Lesson: the old "nexus" column for repo-001..004 includes runs from before the nested-path fix and must not be used as a baseline.
- Static undefined-name check (`verification/names.py`, run inside both probes): a verified result with a name that is read and bound nowhere becomes FAILED with file:line. 0 false positives over the 164 known-good solution and starter folders. Then 12/15 on five repeats of stock, mdlite and scheduler (stock 5/5); the 3 misses were logic clauses the shipped tests never exercise (mdlite precedence twice, one scheduler), each a false claim, and the repair branch did not fire in any of the 20 latest runs because the solo probe said verified. Remaining weakness is clause coverage, not names. I could not show from the records that the name check itself fired.

## Findings that shape the design
- A one-task probe (repo-001, gpt-6-luna) gave all three systems 14/14. Claude Code ran solo (0 subagent calls), dsh made 2 subagent calls, NexusAgent built a 3-node sequential chain (6 agents, 505 s vs 240 s and 297 s; timings are noisy, three systems ran at once).
- `rigor="minimal"` is told to produce "a short ordered workflow", so it never runs anything in parallel, and it always pays an architect model call first.
- The engine already supports fan-out and fan-in: the studio DAG runs departments in parallel with `join="all"` and artifact contracts (`expected_artifact_paths`). Files move between nodes as run artifacts, mounted as `upstream/` into the next sandbox (1 MiB budget).
- `GenerateWorkflowRequest.input_files` still rejects nested names even though `sandbox_files` on a run accepts them.

## Plan
- [ ] `architect/complexity.py`: deterministic assessment (prompt size, number and size of input files, deliverable paths named, units the prompt lists) returning level solo | sequential | parallel plus a reason. No model call unless the signals disagree.
- [ ] `architect/solo.py`: build a `WorkflowSpec` of start + one sandbox node without calling the architect (saves its latency and cost for light tasks).
- [ ] API: `rigor` gains `auto` (new default), `solo`, `parallel`; `minimal`/`standard`/`full_studio` keep their meaning. Response reports the chosen level and why.
- [ ] Parallel planner: one model call that returns units with owned paths and an interface contract; reject plans whose owned paths overlap or that have fewer than 3 units; build contract node -> N sandbox nodes -> integrator (`join="all"`) -> verification.
- [ ] Escalation: a solo run that ends FAILED/UNVERIFIED is retried once at the next level with the failure evidence; never more than one escalation.
- [ ] Tests: classifier table, disjoint-path validation, solo spec compiles, parallel spec compiles and runs in order with a fake supervisor.
- [ ] Benchmark: `--mode auto|solo|sequential|parallel` in the adapter; run the 10 repo tasks plus one larger parallelisable task; report pass rate, false claims, wall time, tokens, and how often the router chose each level and was wrong.

## Success criteria (written before measuring)
- Light tasks: no accuracy loss versus today and a lower median time.
- Heavy task: parallel beats sequential on wall time without losing accuracy; otherwise parallel stays opt-in.
- Misroute rate reported; if solo-then-escalate is no better than always-sequential, the router is removed.

## Open risks
- Parallel workers need the same interface understanding; the contract node is what prevents drift, and it is the part most likely to fail.
- `NEXUS_SANDBOX_MAX_CONCURRENT` and Docker memory (about 6 GB) cap how many workers really run at once.
- 1 MiB upstream budget limits how much one integrator can receive.

# Phase 33 — Clarify, propose and recommend before building a team (backend + web built; not yet seen in a browser)

## Progress notes (Phase 33)
- Built: `architect/clarify.py` (limits enforced in code: <= 4 questions, 2-4 choices, one recommendation per group, distinct levels, no cost field, invalid card retried then built instead of blocked), `POST /api/v1/architect/propose`, `generate-workflow` accepts `decisions`, `assumptions`, `plan_level` and records them on the conversation message and audit log, web `ProposalCard` in the chat (first message of a task only, never for hand-off studio buttons or follow-ups), vi/en strings.
- Deviations from the plan: the proposal card itself is not stored (stateless endpoint; the decisions are stored with the user message), types live in the architect module instead of core-schema, and the speed shown is a label (fast/medium/slow) rather than seconds.
- Checks: 12 new clarify tests, 266 backend tests pass, mypy back at the 22-error baseline, web lint/tsc/55 tests pass.
- Not done: the question-quality evaluation (remove one clause from 8 tasks and see whether a question surfaces it), and a visual check of the card in a running browser.
Goal: for a request that is unclear or has several reasonable ways to be built, ask a few targeted questions, then show 2–3 options with a recommended one, like Claude Code's plan mode. A clear request skips all of it.

## Findings that shape the design
- `ConversationMessage.role` is checked to `user|team|note` and has a JSONB `meta`, so clarification and proposal cards can be `team` messages with `meta.kind` and need no migration.
- `POST /api/v1/architect/generate-workflow` builds and starts the team in one call; the quickbar, the Copilot and the benchmark adapter all call it directly. Anything new must stay opt-in so automatic callers (service keys, benchmark) are never blocked waiting for an answer.
- Phase 32's complexity assessment decides how many options are worth showing (a light task gets none).

## Plan
- [ ] Schema in core-schema: `ClarifyQuestion{id, text, options[{label, description, recommended}], allow_other}`, `PlanOption{id, level, summary, agents, est_seconds, tradeoffs, recommended, reason}` (no cost field: the user is not shown cost), `PlanProposal{assumptions, questions, options}`.
- [ ] `architect/clarify.py`: one model call returning `PlanProposal`; hard limits (≤4 questions, 2–4 options each, exactly one recommended per question and per proposal); drop any question whose answer is already in the prompt or the input files; `status = ready` when nothing needs asking.
- [ ] API: `POST /v1/architect/propose` (returns proposal or `ready`), and `generate-workflow` accepts `answers` and `chosen_option_id`; default `interactive=false` keeps today's behaviour for service keys.
- [ ] Persist the proposal and the answers as conversation messages (`meta.kind = clarification | proposal | answer`), so a thread resumes where it stopped and the audit log records what was chosen.
- [ ] Answers are appended to the requirement as an explicit "Decisions made with the user" block that the architect must treat as binding.
- [ ] Web: question cards with a recommended badge, free-text "Other", and a one-click "Use recommended"; the quickbar shows a compact version.
- [ ] Tests: limits and one-recommended invariant, clear prompts skip questions, answers reach the architect prompt, non-interactive callers are never blocked, tenant scoping on the stored messages.
- [ ] Evaluation (weak by nature, say so): take 8 fully specified tasks, remove one binding clause from each prompt, and score (a) did a question surface the missing clause, (b) questions asked per task on the untouched prompts (burden; target ≤1 on average), (c) pass rate when a scripted user answers with the recommended option versus no clarification.

## Open risks
- Over-asking is the failure users notice first; the default must be "ready" unless an answer would change the plan.
- A model-written recommendation can be confidently wrong; options must state the trade-off, not only a verdict.
- The time estimate in the options is only as good as the Phase 32 calibration data; label it as an estimate. Cost is not shown to the user (decided by the user), though the recommendation may still weigh it internally.


# Phase 34 — Units mode, clause-test experiment, big task (results in benchmarks/code-tasks/REPORT.md, "Giai đoạn 32")
- Parallel execution is NOT built. Findings: every node of a run shares one execution lock (`execute_node`), one container and one working directory, so even the studio's "parallel departments" run one at a time. Next step if wanted: a per-node working directory in the supervisor plus a lock that lets sandbox nodes overlap; the strict xfail `test_units_run_at_the_same_time` marks the spot.
- Built instead: `rigor="units"` (planner returns >= 3 units that each own separate files and a shared contract; overlapping plans are rejected and the model is shown why; one integration node mounts the units' files via `mount_artifacts_from`). Runs one unit after another.
- Fixed from the big task: capsule fields now clipped to schema limits; a sandbox node with declared deliverables cannot be VERIFIED before those files exist.
- Clause-test requirement (`min_added_tests`) measured worse than none; kept as an opt-in node field, default 0.
- Not done: question-quality evaluation for Phase 33, a visual check of the question card, the real parallel engine change, one benchmark task only for the units mode (n = 3).


# Phase 35 — Local execution mode with an execution policy (branch `feature/local-execution-policy`)
Goal: run agent code on the user's own machine without Docker, with the layered approach Cursor and Antigravity use: an OS-level sandbox, a Deny > Ask > Allow policy, secret-file protection, no network by default. Stays opt-in; the Docker and hosted paths remain the default and are not touched.

## Findings that shape the design
- `ComputerProvider` (`packages/computer-sandbox/nexus_computer_sandbox/supervisor.py:51`) is a Protocol (create, destroy, shell, upload, download, files, screen_frame) with `DockerSandboxProvider` and cloud drivers behind it, and the supervisor has `add_provider`. A local provider plugs in without changing the engine.
- Docker today also gives the run a fixed Python image. A local provider runs the host interpreter, so reproducibility of the verification probe must be re-checked (benchmark below).
- Seatbelt (`sandbox-exec`) exists only on macOS, is marked deprecated by Apple, and cannot filter the network per host: network is all-or-nothing. Windows is not researched; do not claim support.
- Server-side dependencies (Postgres RLS, Redis, Celery, Qdrant) are a separate step (Stage B) and are NOT part of Stage A.

## Stage A — policy and sandbox (macOS only)
- [x] `execution_policy.py`: rule model with Deny > Ask > Allow precedence; a Strict profile that ignores the allowlist; default rules deny reads of `.env`, `~/.ssh`, `~/.aws`, keychains and `.git/config` credentials; no allowlisted domains by default.
- [x] Sensitive-write rule: creating or editing executable or config files (hooks, `.vscode`, shell rc, `sandbox.json`-style files) is an Ask, never an Allow (the Antigravity RCE chain).
- [x] `LocalSandboxProvider` implementing `ComputerProvider`: per-run directory under a temp root, commands run through `sandbox-exec` with a generated profile (write only inside the run directory, no network unless the policy grants it), timeout and output cap as in the Docker provider.
- [x] Wire as a provider name `local`, chosen by configuration; `docker` stays the default.
- [ ] Approval flow: an Ask result reuses the existing approval cards; headless callers (benchmark, service keys) get Deny, never a hang.
- [x] Behaviour tests (direct, not benchmark): `cat .env` is blocked, writing outside the run directory fails, a network call fails with no grant, `python -m unittest` runs, files uploaded and downloaded round-trip, a path escape (`../`, symlink) is rejected, timeout kills the process tree.
- [ ] Docs: what the local mode does and does NOT protect (no per-host network filter, macOS only).

## Gates before moving on (stop and re-plan if any fails)
1. Existing test suite passes; mypy stays at the 22-error baseline in 8 files.
2. Benchmark under the local provider versus the Docker baseline, same tasks and model: repo tasks `nexus_auto` baseline 12/15, `minisql` 2/3. Samples are small, so only a large drop is detectable; a drop means find the cause (blocked pip, blocked path, interpreter difference) before continuing.
3. The behaviour tests above are the main safety evidence, not the benchmark.
4. No code edits while a measurement runs (bind mounts; see lessons).

## Stage B — lightweight single-user profile (only after Stage A is accepted)
- [ ] Embedded database instead of Postgres, in-process queue instead of Redis/Celery, Qdrant optional. Tenant isolation currently rests on RLS: the embedded profile needs application-level tenant filtering plus tests; the Postgres path stays the default. Scan: 7 Postgres-specific files, 16 RLS statements, 17 Redis files, Celery tasks in `apps/api/app/workers/jobs.py`, 6 Qdrant files.

## Stage C — packaging (unresearched)
- [ ] Windows isolation approach, bundling the Python backend into the Electron app, dmg/exe.

## Review
### Stage A, first part (done in this branch)
- Built: `execution_policy.py`, `local_provider.py` (Seatbelt), plugin `sandbox.local` (listed but disabled in `default.yaml`), `NEXUS_SANDBOX_PROVIDER` picks the default provider (still `docker`). Enable with a patch file (`sandbox-local` `disabled: false`) plus `NEXUS_SANDBOX_PROVIDER=local`, and the API must run on the macOS host, not in a container.
- Checks: 48 new tests pass on macOS (policy text, then real commands under the sandbox); 346 passed / 31 skipped in the Linux test container (macOS-only tests skip there); mypy back at the 22-error baseline after fixing a platform-narrowing error. Gate 2 partly met: all 83 benchmark tasks give the validated outcome through the local provider (reference solution passes the hidden tests, untouched starter fails), 11 s for 166 runs, host Python 3.12 versus 3.11 in Docker with no difference seen.
- Found while testing (kept as comments in the code): a bare "exit code != 0" passes when the sandbox profile itself is broken, so blocking tests now require the kernel's "not permitted" message; Seatbelt regex does not accept `A-Za-z` ranges; a deny of all of `file-read*` makes the shell's `cd` fail; mixing `file-read*` with `file-read-data` lets the narrower allow override an earlier deny.
### Stage A, second part (done in this branch)
- Built: an Ask from the local policy now goes through the existing approval boundary (`external_action`, same `computer_guard`, same approval cards and "allowed once" grants as destructive commands); `execute_shell` sets a context variable with the approved command so the provider does not refuse it again. No guard means an error, never a hang. One file cannot grow past 1 GiB (`RLIMIT_FSIZE`; macOS enforces no memory or process cap reliably, written down in the README). Templates no longer say `/workspace` (they said "working directory", verify commands use `.`), because the local mode has no such path. Docs: "Local mode" section of `packages/computer-sandbox/README.md`.
- Run the API and worker on the host: `scripts/run-local.sh` (setup, migrate, api, worker), `scripts/load_env.py`, `docker-compose.host-ports.yml` (only Postgres, Redis, Qdrant), `nexus_plugins/local-mode.yaml`. Checked: migrate and api start work; worker needs `--pool=threads` and no `--beat` on macOS (the default prefork pool fails with "not enough values to unpack", the embedded beat fails with "'Celery' object is not callable").
- Gate 2 with real agent runs (`gpt-6-luna`, `nexus_auto`, API and worker on the host, local provider):
  - First run: repo tasks 12/15 (stock 5/5, scheduler 5/5, mdlite 2/5), `minisql` 1/3 (356-474 s). Reading the failed run found a REAL bug: TMPDIR was inside the run directory, so the verification gate copied the working directory into a temp folder inside it, over and over (`.tmp/nexus-gate-x/.tmp/nexus-gate-x/...`). Docker does not show it because `/tmp` is a separate tmpfs. Fixed: scratch space (TMPDIR and HOME) now lives beside the run directory, removed on destroy; test added.
  - After the fix: `minisql` 3/3 (48-86 s, Docker baseline 96-126 s); repo tasks 11/15 (stock 5/5, scheduler 5/5, mdlite 1/5).
  - mdlite fell from 8/10 (earlier Docker runs) to 3/10 locally; every failure is the same single hidden test (`*a `b*` c`). Same-day control, Docker provider through the same host API, same code and model: mdlite 3/10. So the drop is model drift between sessions, not the provider. Lesson recorded.
  - Totals same day: local 5 of 5 stock, 5/5 scheduler, 3/10 mdlite, 3/3 minisql; control 3/10 mdlite (stock smoke 1/1). Samples are small: this shows no large regression, not equality.
- Checks: 346 backend tests pass in the Linux container (macOS-only tests skip there), 53 macOS tests pass, mypy at the 22-error baseline.

### Stage B decision (not built, on purpose)
Replacing Postgres, Redis, Celery and Qdrant with embedded stores touches 17 migrations written for Postgres (JSONB, row-level security, `set_config` for tenant scope), 7+ app files, Redis pub/sub event streams, ~11 Celery tasks and 6 Qdrant files. It cannot be verified to keep tenant isolation without a large new test suite, and the Docker lag comes from the Docker VM, not from those services. The cheaper route that removes Docker with NO application change: run the same Postgres 16 and Redis 7 natively (Homebrew `postgresql@16`, `redis`) and Qdrant in its embedded or binary form, and start the app with `scripts/run-local.sh`. Needs the user's go-ahead to install software; nothing was installed. Until then `docker-compose.host-ports.yml` runs just those three containers, which is far lighter than the whole stack.

### Stage C findings (research only; nothing built)
- Windows: Cursor's documented Windows sandbox runs inside WSL2 (same restrictions as Linux); a native sandbox exists but is limited (PowerShell restricted language mode). Third-party analysis says no single Windows primitive sandboxes an agent cleanly; the working patterns are WSL2, or a restricted token plus dedicated user. Codex documents an experimental restricted token derived from an AppContainer profile. Sources: https://cursor.com/docs/agent/tools/terminal.md, https://agentpatterns.ai/security/windows-sandbox-primitives-coding-agents/, https://developers.openai.com/codex/sandbox
- dmg/exe: the common pattern is to freeze the Python backend with PyInstaller (a directory, not one file, built on each target OS), have Electron start it as a child bound to 127.0.0.1 on a dynamic port with an authenticated health check, and package with electron-builder (dmg on macOS, NSIS on Windows). Signing and notarization are a separate step. The backend here (CrewAI, AutoGen, litellm, Celery, Postgres drivers) will need hidden-import work and a large bundle; it also still needs Postgres and Redis, so the Stage B decision comes first. Source: https://github.com/sodejm/AncestryLLM/wiki/DESKTOP_SIDECAR
- Not done: an embedded profile, the Windows sandbox, the packaged app, a browser check of the approval card (it reuses the existing one, not re-checked here).
