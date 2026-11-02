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
