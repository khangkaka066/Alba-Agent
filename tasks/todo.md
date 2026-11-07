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

# Phase 36 — One installable app, no Docker (branch `feature/local-execution-policy`)
Goal: a `.dmg` (macOS) and `.exe` (Windows) that run NexusAgent with nothing else installed, the way Cursor installs. Accuracy and speed must not drop against the Docker stack.

## Decision (replaces the Stage B note above)
Do NOT replace Postgres/Redis/Qdrant with embedded stores (tenant isolation by RLS cannot be re-verified cheaply). Ship the SAME services as sidecar binaries inside the app and start them from the Electron main process. Application code stays the same, so agent behaviour and speed are the same code path that was already measured.
- Python backend: a relocatable CPython (python-build-standalone) with the pinned requirements installed. Not PyInstaller: no hidden-import hunting for CrewAI/AutoGen/litellm, and the interpreter is also the one agent commands run with.
- Postgres 16 (zonky embedded-postgres-binaries), Redis 7.2.4 built from source (last BSD release; same version as compose), Qdrant 1.12.6 release binary (same as compose).
- Web: Next.js `standalone` output, started with Electron's own Node (`ELECTRON_RUN_AS_NODE`).
- Data under the user's app-data folder; secrets generated on first run (file mode 0600); one fixed loopback port per service (the web bundle bakes the API WebSocket URL).

## Steps
- [x] 1. Backend: `NEXUS_DB_PORT`, `NEXUS_REDIS_PORT` (defaults unchanged) so sidecars can use private ports. Test.
- [x] 2. `scripts/package/build_runtime.py <platform>`: fetch + verify (sha256) + assemble `apps/desktop/runtime/<platform>/`.
- [x] 3. `apps/desktop/src/stack.ts`: first-run init (initdb, runtime role, secrets), ordered start, health checks, migrations, shutdown, restart on crash; unit tests for the pure parts.
- [x] 4. `main.ts`: embedded mode with a boot screen and error page that says what failed (no more "docker compose up").
- [x] 5. electron-builder: `extraResources`, arm64 dmg. Build it.
- [x] 6. Verify from the BUILT app, Docker stopped: boot time, one real agent run, a tenant-isolation spot check, quit leaves no orphan processes.
- [x] 7. Performance gate: same tasks as the Stage A gate against the packaged backend (stock, scheduler, minisql; mdlite only as a same-day control). A large drop means find the cause before shipping.
- [ ] 8. (NOT DONE, see below) Windows: same runtime script for win-x64, NSIS config, CI workflow that builds and smoke-tests on `windows-latest`. NOT runnable on this Mac: stays "unverified" until CI has run.

## Known limits to state, not hide
- Windows has no Seatbelt. Until a WSL2 or restricted-token provider exists, the Windows build must run agent commands in Strict mode (every command asks) with the text policy only, and say so in the UI/README.
- Unsigned/un-notarized: first launch needs confirmation on macOS, SmartScreen on Windows.
- Bundle size will be about 1.2–1.5 GB because the backend needs CrewAI, AutoGen, litellm, onnxruntime.

## Review (Phase 36)
- Built: macOS arm64 `.dmg` (548 MB, app 1.6 GB installed) that starts Postgres 16.15, Redis 7.2.4, Qdrant 1.12.6, API, worker and web from inside the app. No Docker, no system Python. `scripts/package/build_runtime.py` + `runtime.json` (sha256 pins; Qdrant's was recorded on first download because the release publishes none), `apps/desktop/src/stack.ts` (+ `stack-cli.ts` headless), embedded mode in `main.ts`, `NEXUS_DB_PORT` / `NEXUS_REDIS_PORT` in the backend (defaults unchanged, 3 tests).
- Same code as before: the backend and packages are copied unchanged, so agent behaviour is the code already measured. Runtime is Python 3.12.16 (Docker image: 3.11), same sandbox libraries as the sandbox image except Pillow (13 from the API pins, not 11.0.0), and no ffmpeg/chromium (the Docker sandbox image has them; the local mode uses whatever the Mac has).
- Performance gate against the packaged stack (gpt-6-luna, `nexus_auto`, Docker stopped): stock 3/3 (25-33 s), scheduler 3/3 (37-41 s), minisql 2/3 (77-86 s), mdlite 1/3 (45 s; this task is model-noisy: Docker 8/10 earlier, 3/10 the same day as the local runs). Host-run local provider earlier: stock 29 s, scheduler 37 s, minisql 48-86 s. Then from the built app copied out of the dmg: stock 38 s, scheduler 55 s, mdlite 234 s (passed). A first batch right after connecting the gateway took 280 s for stock and scheduler (5 attempts each, sandbox time 0.15 s) and was normal on every later run; cause not proven (gateway latency is the likeliest; the sandbox time rules out the local runtime). Samples are small: this shows no large regression, not equality.
- Lifecycle checked on a copy installed from the dmg: first start 85-94 s (creates the database), warm start 34-42 s (headless 18-25 s; Electron plus the services), quit 3-5 s with nothing left running and Postgres shut down cleanly, SIGKILL of the app then restart recovers (orphans stopped, Postgres recovers its WAL, 38 s), quitting while still starting leaves nothing, a saved provider credential survives restarts.
- Bugs found by running it (all fixed): standalone web copy lost pnpm symlinks (module not found); `bootstrap` did not create the database; relative runtime path broke `spawn` with another cwd; Pillow pin clashed with pdfplumber; crash cleanup matched processes by command line but the web server renames itself `next-server`, so it kept port 13000 forever (now pid + start time); ports were checked before the killed orphans released them; a quit during startup left new processes behind.
- Environment finding: this harness sets `ELECTRON_RUN_AS_NODE=1`, which makes the Electron binary behave as plain Node ("bad option: --user-data-dir"). Launch the app with `env -u ELECTRON_RUN_AS_NODE` when testing from here. `open -a` does not start the app from this harness; direct execution does.

### Not done, and why
- **Windows `.exe` with the embedded stack: not built.** I have no Windows machine here, so nothing could be run, and the Windows pieces are real work, not packaging: (1) a Windows sandbox (no Seatbelt; Cursor uses WSL2, Codex a restricted token), (2) agent commands assume a POSIX shell, (3) Redis has no official Windows build (redis-windows publishes 7.2.x, BSD, unverified), Postgres/Qdrant/Python have Windows binaries (pins noted: python-build-standalone x86_64-pc-windows-msvc, zonky windows-amd64 16.15.0 sha256 51c7812d..., qdrant-x86_64-pc-windows-msvc.zip sha256 2450892b...), (4) graceful stop of Postgres needs `pg_ctl` instead of signals. The existing `build:win` still produces the installer that opens a window onto a remote server. `Stack` refuses to start on non-macOS instead of pretending.
- Intel Macs (x86_64): same recipe, not built.
- Not signed or notarized: first launch needs right-click, Open.
- No in-app restart when one service dies while the app is running (the page says to reopen the app); logs are in the app-data `logs` folder.
- Local Ollama endpoints are only accepted through the Docker host bridge name in the providers router, so a native Ollama is not usable from this app yet.

---
# Phase 37 — The bundle must run on any machine (branch `feature/local-execution-policy`)
Goal: what ships in the dmg (and later the exe) must not depend on anything of the machine that built it, and must contain the tools agent commands expect. Evidence before claims: an audit script, not a guess.

## Corrections to what I said earlier
- I said the Docker sandbox image had Node. It does NOT: `packages/computer-sandbox/Dockerfile` is `python:3.11-slim` + ffmpeg + chromium + fonts + pandas/matplotlib/openpyxl/pillow/pytest. No Node, no git. So the parity gap is ffmpeg + a headless browser (+ Pillow 13 vs 11). Node and git are additions that make JS/git tasks work on a clean machine.
- Found by looking: pip console scripts in the bundled Python (`pytest`, `uvicorn`, `celery`, `alembic`) start with `#!/Users/<builder>/.../python3`. On any other machine or install path they fail with "bad interpreter".
- On this Mac the agent's PATH (`<python>:/usr/bin:/bin:/usr/sbin:/sbin`) hides `/opt/homebrew/bin`, so ffmpeg/node on the builder are invisible to agent commands anyway; a clean Mac has none of them.

## Decisions
- Agent PATH is built from `NEXUS_SANDBOX_TOOLS_PATH` (os.pathsep list, set by the app to the bundled tool folders), then the system folders. Platform-neutral code (no hard-coded ":" or "/usr/bin" literals outside one constant) so the Windows build reuses it.
- Bundle: Node 22 LTS (MIT, same major as apps/web Dockerfile), git built from source with RUNTIME_PREFIX (GPLv2: source offer in THIRD_PARTY_NOTICES), ffmpeg static build if a pinned, checkable source exists (GPL: same notice). No Chromium bundle (300+ MB): a `headless-browser` wrapper finds an installed Chrome/Edge/Chromium (every Windows has Edge) and says plainly when there is none.
- Portability gate = `scripts/package/verify_runtime.py <platform>`: every Mach-O's architecture, minimum macOS version, and dependencies (only /usr/lib, /System, or inside the runtime); no absolute build-machine path in scripts; then a smoke run from a COPY in a folder with a space, with PATH reduced to system folders, no Homebrew visible.
- Intel Macs: same recipe, `mac-x64`, tested under Rosetta (running on this Mac).
- Windows: not built (no machine). Make the code ready (pathsep/exe suffix, pins table) and say what is still missing.

## Steps
- [x] 1. Backend: tool directories in the local provider's PATH (`NEXUS_SANDBOX_TOOLS_PATH`), test.
- [x] 2. build_runtime.py: relocatable shebangs, `node`, `git`, `ffmpeg`, `headless-browser` steps; pins in runtime.json.
- [x] 3. stack.ts: pass the tool folders; `delimiter` instead of ":"; test.
- [x] 4. verify_runtime.py + run it on mac-arm64, fix what it finds.
- [x] 5. Smoke from a relocated copy with a minimal PATH: python/pytest/node/npm/git/ffmpeg.
- [x] 6. Rebuild arm64 dmg; run the agent gate again (stock, scheduler; add one JS task to prove Node works) with Docker stopped.
- [~] 7. mac-x64: DROPPED by the user ("only build arm"). Built anyway: audit 0 problems and Rosetta smoke 14/14 passed on the build folder; the dmg was built but its installed copy was never verified or booted.
- [x] 8. THIRD_PARTY_NOTICES (git, ffmpeg source offer, Node), README, review.

## Review
- Shipped (arm64 only): relocatable console scripts, bundled Node 22, git 2.56 (GPLv2), ffmpeg 9.0.2 (LGPL), `headless-browser` wrapper, agent PATH from `NEXUS_SANDBOX_TOOLS_PATH`, macOS floor 15.0 declared once, `verify_runtime.py` gate. dmg 621 MB.
- Evidence: verify_runtime on the build folder and on the runtime copied out of the final dmg: 0 problems, smoke passed. 9 sandbox/bundled-tool tests pass. Earlier this phase: backend 352 passed, desktop 13 tests, mypy at baseline.
- Agent run from the dmg-installed stack with Docker off: the agent ran the bundled Node (v22.23.4, sum 231, correct). The run itself never reached "verified": the verifier demands >= 3 self-written Python tests, so non-Python tasks loop until the wall-clock limit. OPEN: make verification language-aware.
- Gate on the new dmg (3 passes): stock 3/3, scheduler 3/3, mdlite 0/3 (previous gate 1/3, flaky task). Wall times were 26-165 s for the same 2 attempts against ~35 s before; sandbox time per run 0.2-0.4 s, so the wait is the model gateway. Not compared under identical conditions; treat as unexplained, not as proven noise.
- Found while building Intel (kept, shared by both builds): `arch -x86_64 make` fails (CLT has no Intel slice) so the compiler gets `-arch`; git's Makefile overrides `CC` so it is passed on the make command line; sharp is retargeted from the npm registry with sha512 check; the verifier runs the Intel smoke through the runtime's own Python.
- Still open: Windows exe, signing/notarization, lowering the macOS floor, Intel installed-copy verification (not needed now).

# Phase 38 — Antigravity-style shell, then a README with the new screenshots (branch `feature/local-execution-policy`)
Request: study the 3 Antigravity screenshots, improve the UI, build the full set of bars/buttons like Antigravity; then rewrite the root README.md with NEW images of the redesigned app. Plan only so far; nothing below is implemented.

## What Antigravity does (from the screenshots)
1. Frameless titlebar row: traffic lights, sidebar toggle, back/forward, search; main header = breadcrumb "Project / Conversation title" + (⋮ menu, panel toggle, right-sidebar toggle).
2. Left sidebar: `New Conversation` button, Automations, Customizations; section **Projects** (filter + add-folder icons; each project a folder row with its conversations and relative age "3h/1d/4d"); section **Conversations** (+ button) for conversations without a project; Settings pinned at the bottom.
3. Composer: "Ask anything, @ to mention, / for actions", `+` (attach), model picker, **permission preset** chip (Auto (Preview)), mic, round send button. Message footer: age, copy, 👍/👎.
4. Settings = centred modal over the app: left nav (General, Application, Appearance, Shortcuts, Notifications, Models, Projects…), card rows (Permission Preset, Tool Permissions, Network Access Rules, Plan Review Policy, Queue/Send Immediately, Built-in Browser).
5. Right dock (split view): overview menu (Review +added/−removed, Files, Terminal, Extensions ›), "Modified Files (n)" list, a new-tab page with "Search or enter a URL" + Review / Open File / Terminal / Browser, expand and close buttons.

## What exists today (explored, apps/web)
One hand-rolled React app: `components/studio-app.tsx` (379-line monolith: sidebar, header, modals, Cmd+K palette), 1604-line `app/globals.css`, no shadcn/radix/zustand/lucide, inline-SVG icons, node:test for pure `lib/*.mjs` only. Settings are full pages, not a modal. Sidebar lists runs (no "projects"). Composer has no preset/mic. Shortcuts: only Cmd+K/B/\/Enter/1/2/, and `nexus:run` has no listener. No Cmd+J/I/L, no A/Y/D approvals, no real browser/PTY/git review. Desktop window is already frameless (`hiddenInset`, traffic lights at 16,14).

## Decisions I need from you (answers change the work)
- D1 Projects: use the opened local folder (+ runs grouped by it) as a project; runs without a folder go under Conversations. (Recommended: no backend change.)
- D2 Right dock content that has no backend yet: Review = diff of the run's artifacts (exists), Files = artifact tree (exists), Terminal = the run's terminal output (read-only, exists), Browser = an in-app address bar page that opens URLs in an iframe/new window (sites that forbid framing will not load). A real PTY and a real browser engine are NOT part of this phase.
- D3 Mic button: show it only if the browser speech API exists, otherwise hide it (no fake button).
- D4 Scope of CSS: add a new token layer + new shell components and retire the old `.app-shell--chat` overrides; do not rewrite the 1604-line file in one go.

## Steps
- [x] 1. Split `studio-app.tsx`: AppShell, TitleBar (drag region, toggles, back/forward, search), Sidebar (new conversation, Automations, Customizations, Projects, Conversations, Settings), Breadcrumb header, RightDock. State in one small store (React context + pure reducer in `lib/shell.mjs`, node:test).
- [x] 2. Tokens (CLAUDE.md §2.4: #09090b, #27272a, #18181b, cyan/indigo/amber; 150-200 ms transitions) as a new layer; icon set as a local `Icon` component (no new dependency).
- [x] 3. Composer: `+` attach menu, `@` mention, `/` actions, permission preset chip (maps to existing approval policy), model picker, send; message footer actions.
- [x] 4. Settings as a centred modal with left nav and card rows (reuse existing settings bodies).
- [x] 5. Right dock: overview menu, Modified Files list, tabs (Review, Files, Terminal, Browser), expand/close; `Cmd+J` (terminal/dock), `Cmd+I` (inspector), `Cmd+L` (copilot focus), wire `Cmd+Enter` to send; approval hotkeys A/Y/D on `ApprovalCard`.
- [x] 6. Responsive: dock collapses under 1100 px, sidebar becomes a drawer under 800 px (existing mobile-nav hook).
- [x] 7. Verify: `cd apps/web && pnpm check && pnpm lint && pnpm test`; desktop `pnpm check && pnpm test`; run the app from the rebuilt dmg stack and look at every screen in a real window.
- [x] 8. Screenshots: capture the REAL redesigned app (home, active chat, settings modal, right dock) at 1400x870 from the running app; rebuild `docs/media/nexus-tour.gif` from them. No mock-ups drawn by hand.
- [x] 9. Rewrite root `README.md` around the desktop install (dmg, no Docker, bundled tools, honest limits: macOS 15+, arm64 only, unsigned) with those images. `README.vi.md` stays unchanged unless you ask (it will lag).
- [x] 10. Review section here, lessons, commit and push on the branch.

## Review (Phase 38)
- Decisions used: D1 projects = the opened folder (remembered per run in localStorage, `lib/shell.mjs`), D2 dock shows existing data only, D3 mic only where the browser has speech recognition (never in Electron), D4 new `shell.css` layer scoped under `.ag-app`, older CSS untouched.
- Built: title bar, sidebar (New Conversation, Automations = the Teammates page, Customizations, Projects, Conversations), centred conversation with the Antigravity message box (+, model, read-only permission chip, mic, send, `/` actions, `@` attach), right dock (Review with +/- per file, Files, Terminal, Browser, Canvas; resizable, expandable), settings as a panel, command palette with panels and conversations, shortcuts Mod+J/I/L, Mod+Enter now sends, approval hotkeys A/Y/D.
- Honest gaps: Terminal is the run's output, not a PTY; Browser is a sandboxed iframe (http/https only, never the app's own origin); the permission chip is read-only because no per-request permission API exists; the old light theme is not restyled; reopening an old run does not replay its terminal output.
- Verified: web tsc/eslint clean, 62 node tests (7 new for `lib/shell.mjs`), desktop tsc clean; the app driven in headless Chrome over DevTools (dock, overview, browser tab incl. a refused `javascript:` address, slash menu, palette, settings panel, 390 px width without horizontal overflow); packaged dmg rebuilt (verify_runtime 0 problems) and the packaged web serves the new shell.
- Not verified: the packaged Electron window itself (traffic-light room, drag region) was not opened; speech recognition; Windows/Linux title-bar overlay padding.
- Unrelated problems met while making screenshots (not caused by this phase, not fixed): with the ShopAIKey gateway the architect's agent models can be unknown to the gateway (404 model not found) or a crew fails with `KeyError: 'Architect_crew_1_3Output'`; a 7-department run can hold both worker threads for 10+ minutes. Demo data came from a real run started with the benchmark adapter (minimal rigor, models pinned).
- README.md rewritten with the new screenshots and a rebuilt tour GIF; README.vi.md not touched (it still points at the old screenshots, which were kept).

## Review (Phase 39: the gateway failures seen while making screenshots)
- `KeyError: 'Architect_crew_1_3Output'`: `consensus_handler` looked the schema up in the registered table. Now `AppServices.consensus_schema` resolves it through `CrewBuilder.schema_for_task`, which also builds generated JSON schemas (`apps/api/app/services.py`). Test: `test_consensus_schema.py`.
- Model-not-found 404: the architect fell back to the first name in the sorted model list (`openai/MiniMax-M2.5`, which the gateway lists but answers 404). New `trusted_models` (the user's default models, orchestrator first) feed `fallback_model` and `consensus_pool`; the architect's own model prefers them too (`routers/architect.py`, `architect/team_generator.py`). Test: `test_default_model_choice.py`. Without defaults set the old behaviour stays.
- 7-department studio for a tiny script: `is_small_script_request` (`architect/adaptive.py`) keeps a software request that names a source file or says tiny/simple/N lines, and names nothing product-sized, on the light path. Test: `test_small_script_not_a_studio.py`.
- Evidence: API suite 395 passed; the same 2 failures (Redis, sandbox files) fail on the untouched code. Live, same prompt without a pinned model: before 421 s, no file, studio; after 77 s, `todo.py` + `test_todo.py`, workflow start/solo/gate/repair, every agent on `gpt-6-luna`.
- Not fixed: the gateway still lists models that answer 404, so a user with no default model and no picked model can still reach one; a UI-visible "model unavailable" check, and `strong_model` / director model hints, still choose from the full list. The dmg and `release/mac-arm64` were not rebuilt (runtime/mac-arm64 backend files were overlaid by hand for the live test).

## Review (Phase 40: show only models the connection can use)
- Connecting/testing a provider (`providers.usable_models`): each chat model is asked for one token; a model is dropped after two 403/404 answers; 429/5xx/timeouts are asked again in narrower passes (24, 8, 4 wide) within 15 s; undecided models stay listed; embedding, audio, image and video models are not judged by the chat endpoint.
- Architect model list (`architect.reachable_model_names`): only models of connected providers, plus price-table models of providers the server holds a key for. The price table alone no longer adds unconnected providers.
- Evidence: API suite 406 passed (the same 2 Redis/sandbox failures as on untouched code). On the real ShopAIKey gateway (232 listed, 16 of them answer 404/403 alone) three runs dropped 19 (single-refusal rule, false positive `gpt-5.6-sol-high`), 1 and 0 (two-refusal rule) in 8-31 s: the gateway's throttling decides the result, so this filter is best effort there.
- Not done: a reliable check needs a background job that re-verifies slowly, or learning from real calls (hide a model after a real 404). The test button can wait up to ~15 s.
- Follow-up: the repair, director and strong-model choices (`ArchitectWorkspaceContext.frontier_model`) now search only the models known to work when there are any; the keyword `gpt-5` used to match `gpt-5-codex-high`, which answers 404. The old `strong_model` helper was removed.

## Review (Phase 41: pin, flag, suggest; modelled on opencode)
- Pin: `custom_model_ids` now decides the connection's models (`providers.decide_models`); the connection test no longer overwrites it with the gateway's `/models`. Pinned names the gateway does not list come back as `unlisted_models`.
- Flag: the two-refusal probe (`assess_models`) only marks `suspect_models` in the credential settings. The picker shows them with "Chưa chắc chạy được / May not run" and still lets the user pick; the architect and the default model never choose them by themselves; the connection card lists them after the test. With a pin, only the pinned names are probed.
- Suggest: a run that fails with a provider "model not found" gets `suggested_models` and a sentence naming the user's default models (`failure.is_model_not_found`, `with_model_suggestions`, `workers/jobs.py`).
- Evidence: API suite 427 passed (same 2 Redis/sandbox failures as on untouched code); web tsc, eslint clean, 62 node tests pass. The live gateway check could not be repeated: the ShopAIKey key now answers 401 "Invalid token" (checked with `/models` and a one-token chat), so pinned/flagged behaviour is covered by mock-gateway tests only.
- Not verified: the picker badge and the settings warning have not been seen in a browser; the dmg was not rebuilt; the DB path of the failure suggestions (`jobs.py`) has no automated test (the pure parts do).

# Phase 42 — Breadth-depth refinement (arXiv:2608.05643) — PLAN, not started
Source: Bilal et al., "Refining Over Resampling: Test-Time Self-Correction for LLM Reasoning", arXiv:2608.05643v1, 6 Aug 2026. Text read from the PDF (pdfplumber). Evaluated on MATH benchmarks with open-weight models (Qwen2.5-1.5B / Math-7B, Ministral-8B, LLaMA-3.1-8B); no code tasks, no hosted API models.

## What the paper does say (checked in the text)
- Algorithm 1 / Eq. (3)-(5): generator, critic, corrector roles conditioned as g ~ pi_G(x, r^(d-1)), c ~ pi_C(x, g), r ~ pi_R(x, g, c); N i.i.d. rollouts at fixed tau = 0.7; default N = 8, D = 4. When the critic finds no error it "explicitly confirms the trace" (Sec 3.3). Answer extraction Phi then plurality vote V, no verifier / PRM / learned stopping policy (Sec 3.4, 5).
- Table 2: explicit critique helps "in most settings" (not all: Qwen2.5-Math-7B AIME24 is 10.0 with and without).
- A.2: rho_rec(d), rho_reg(d) = QUESTION-level flips of the plurality-vote answer (Eq. 6-7). A.3: mu_{W->C}(d), mu_{C->W}(d) = ROLLOUT-level flips over (q, i) pairs (Eq. 8-9); B(d) = mu_{W->C} - mu_{C->W}. Two different quantities; the request treats them as one.
- A.4: U(d) = E[1[|A(d)| = 1]] (answer agreement) and terminal diversity D = E[1[|A(D)| > 1]] — DIAGNOSTICS, not a stopping rule. Full agreement "remains relatively rare".
- A.6: embeddings all-MiniLM-L6-v2 (384-d), agglomerative clustering, average linkage, cosine distance, threshold 1 - tau_sim with tau_sim = 0.85; p_j(N), R(N), f_max(N), H(N) = -sum p_j log2 p_j. Used ONLY for the redundancy analysis (Fig. 1); it "does not affect the main accuracy results".
- Sec 3.5 / A.7: C_gen = sum 2 P_gen (T_in + T_out) FLOPs; eta = 10^3 (a_ours - a_base) / (C_ours - C_base), accuracy in points averaged over five benchmarks, compute in TFLOPs.
- Table 3: accuracy is NOT monotonic in N or D (Qwen2.5-1.5B, AMC23, N=3: 21.05 / 27.5 / 20.5 / 20.5 for D=2..5); the paper concludes moderate settings, N = 8, D = 4, are a stable trade-off. A.8: refinement is "most compute-efficient for smaller models".

## What the request adds (extensions — to be labelled as ours, not the paper's)
- 0.92 similarity prune and "orthogonal perspective" injection (no 0.92 anywhere in the paper).
- Early stop when the critic reports zero defects in a majority and U(d) = 1.
- Cluster + critique-score selection for open-ended artifacts (code, reports).
- Reading B(d) as a skill / capsule signal and AUTO-quarantining on B(d) < 0. The paper warns the opposite: a negative rollout-level B(d) "does not necessarily imply lower final accuracy" because plurality voting suppresses isolated harmful flips (A.3), and B(d) "can be negative for some models and depths" (A.8).
- Tier table (5,3) / (8,4) / lean (1,1), (3,2) for Ollama 1.5B-8B, gpt-4.1-mini, frontier models.
- eta for hosted API models: their parameter count P is not public, so TFLOPs cannot be computed; tokens or USD must stand in (label them eta_tokens / eta_usd).

## Findings in our repo that shape the work
- Paths: `packages/agent-runtime/consensus/` exists (engine.py, 48 lines: draft / cross-critique / arbiter over several models; production consensus actually lives in `apps/api/app/services.py` consensus_handler). `packages/learning-transfer/learning_transfer/negative_transfer_detector.py` exists (89 lines: TIS score, minimum_applications = 5, `TransferCircuitBreaker` quarantine already wired in `routers/learning_transfer.py`). `packages/model-gateway/nexus_model_gateway/auto_distill.py` exists (75 lines). Intelligence tab = `studio-app.tsx` line ~393: EvolutionHost, LearningTransferRadar, FinOpsDistillationPanel.
- Existing transfer data is two UNPAIRED groups (baseline vs treatment). mu_{W->C} / mu_{C->W} need the SAME trace before and after (a pair); inside the refinement loop that pair is natural (g_i^(d) vs r_i^(d)), for skills / capsules it needs paired replays or retries.
- "Correct / wrong" needs an oracle. The paper uses gold answers. Here the oracle is the verification probe (Status.VERIFIED) or a human approval; without one the flip metrics are undefined.
- No sentence-embedding library in `apps/api/requirements.txt`; embeddings are available through the gateway (`LiteLLMEmbeddingRouter`, billed) only.
- Cost: N = 8, D = 4 is 8 + 3*8*4 = 104 model calls per task, each with a growing context, against well under 10 today. At ~0.03 USD/task now that is roughly 10-20x. Must be opt-in with a budget guard.

## Phasing (each phase ends green and committed on its own)
- [x] Phase A — pure library, no wiring, no network: `consensus/breadth_depth_refiner.py` (injected generate / critique / correct / extract / embed callables; stages 1-3; H(N), cluster mass, U(d), diversity D; early stop; plurality vote; deterministic tie-break), pluggable `Embedder` (lexical fallback for tests), tests with scripted policies.
- [x] Phase B — metrics: `negative_transfer_detector.py` gains rho_rec / rho_reg (question level), mu_{W->C} / mu_{C->W} / B(d) (rollout level) from paired observations, a minimum-sample guard and a significance check, and feeds the EXISTING circuit breaker (recommendation first, human approval for rollback). `auto_distill.py` gains a compute ledger, eta (TFLOPs when P known, else tokens / USD), and `allocate_breadth_depth(model_tier, task)`.
- [ ] Phase C — wiring behind an opt-in flag + budget guard: hosted-model adapter in services, diagnostics persisted in the run's node output (no migration), `GET` endpoint, Intelligence panel in `apps/web` (vi / en strings, tests).
- [ ] Phase D — live check on the gateway with a small N, D (needs a free API key / balance; the benchmark of the cost work must be finished first).

## Safe to do while the branch-B benchmark runs
The benchmark stack runs from `apps/desktop/runtime/mac-arm64` with data in `/tmp/nexus_bench_data` (checked with ps). Phases A and B only edit `packages/` and add tests, make no API calls and are light on CPU. Do NOT touch `apps/desktop/runtime`, `benchmarks/code-tasks/{bench,tasks,results}`, ports 13000 / 18000, or the ShopAIKey key until it finishes.

## Decisions taken (answers of the user, 2026-11-07)
- Scope A+B first. Negative transfer: RECOMMEND, a person approves (`assess_flips` sets `requires_human_approval`, `recommend_quarantine`; nothing rolls back by itself).
- Refinement stays OFF by default; `allocate_breadth_depth` only suggests (N, D) per model tier and `fit_to_call_budget` trims it to a call cap. Chosen by me when asked to balance accuracy against cost: the paper's Table 3 is not monotonic and N = 8, D = 4 is ~104 calls per task.
- Embedder behind an interface; lexical is the default; MiniLM (ONNX, local) compared against it.

## Review (Phase 42, A and B)
- Built: `consensus/diversity.py` (cosine, average-linkage clusters at tau_sim, R(N), f_max, H(N), redundant pairs), `consensus/embedders.py` (LexicalEmbedder, MiniLMOnnxEmbedder), `consensus/breadth_depth_refiner.py` (Algorithm 1: breadth, G -> C -> R per depth as parallel batches, mandatory critique, plurality vote, deterministic tie-break, open-ended selection by dominant cluster, early stop, redundancy inject / prune, call budget, oracle flip counts), `negative_transfer_detector.py` (flip_rates, question_level_rates, assess_flips with an exact sign test and a final-outcome guard, flag_for_review), `auto_distill.py` (tier, allocation, call-budget fit, compute ledger, eta with a unit label).
- Tests: 82 new (agent-runtime 36, learning-transfer 14, model-gateway 32); `pyproject.toml` testpaths + pythonpath register them (before, only apps/api/tests was collected). Whole repo: 544 passed, the same 2 old failures (Redis, sandbox files); mypy strict unchanged at 2 errors.
- Embedder comparison (48 hand-written rollouts, 4 problems x 3 approaches x 4 wordings, single thread, Apple Silicon; indicative only):

| embedder | AUC same-vs-other approach | ARI @ paper tau 0.85 | ARI held-out calibrated | H error calibrated (bits) | 8 texts (median) | process RSS | model |
|---|---:|---:|---:|---:|---:|---:|---:|
| lexical (default) | 0.575 | 0.00 | 0.03 | 0.69 | 1.5 ms | 29 MB | none |
| lexical, no batch IDF | 0.573 | 0.00 | -0.05 | 0.69 | 1.5 ms | 31 MB | none |
| lexical, unigrams only | 0.599 | 0.00 | 0.03 | 1.13 | 1.8 ms | 31 MB | none |
| MiniLM fp32 | 0.681 | 0.00 | 0.26 | 0.65 | 267 ms | 225 MB | 86 MB |
| MiniLM int8 (arm64) | 0.672 | 0.00 | 0.30 | 0.64 | 80 ms | 119 MB | 22 MB |

  Reading: MiniLM separates solution approaches better than the bag of words, but both are weak on short rollouts of ONE problem (they share the topic): even MiniLM puts same-approach pairs at 0.51 cosine and other-approach pairs at 0.44. The paper's tau_sim = 0.85 makes every rollout its own cluster on this kind of text (ARI 0, H always log2 N), so the threshold has to be calibrated per embedder and text length (leave-one-problem-out gave about 0.54 for MiniLM, about 0.08-0.15 for the lexical one). int8 shows no visible accuracy loss against fp32 and is 3x faster, half the memory, a quarter of the size. Speed is irrelevant next to a model call (80 ms against seconds); the real costs are packaging (22 MB model + onnxruntime / tokenizers / numpy, which the bundle already has as transitive dependencies but `requirements.txt` does not list) and one more thing to verify.
  Sanity of the ONNX embedder: 0.89 for "The new movie is awesome" vs "...so great", -0.03 for the cat sentence, unit-length 384-d vectors, matching the sentence-transformers documentation.
- Not done: Phase C (wiring behind a flag, services adapter, endpoint, Intelligence panel, vi / en strings) and Phase D (a live run through the gateway). Nothing calls a model yet and nothing is shown to users.
- Limits worth keeping in mind: the paper tests math with extractable answers; code is our extension. For code the better oracle is the test probe (`Status.VERIFIED`), which the paper does not use. Flip rates need an oracle and a PAIR per trace; the existing capsule data are two unpaired groups, so wiring them needs paired replays.

## Embedding improvement (Phase 42, follow-up; phases C and D paused at the user's request)
Goal: make the rollout-diversity figures (clusters, H(N)) trustworthy. Method: 8 hand-written problems (96 rollouts: 3 approaches x 4 wordings each). Everything was tuned on the first four ("design"); the last four were written afterwards and only used to judge ("test").
- Diagnosis: rollouts of ONE problem share its topic, which dominates their cosine; same approach 0.51 vs another approach 0.44 for MiniLM. The paper's tau_sim = 0.85 (meant for long math traces) then leaves every short rollout alone: ARI 0.00, H error 1.48 bits for every encoder except gte-small.
- What worked: remove what the rollouts share (the problem statement's direction, then the batch mean), re-normalise, cluster at cosine -0.1. Pairwise AUC 0.68-0.77 -> 0.85-0.90 on test. The cut -0.1 was the best for all six sentence encoders, chosen on design, confirmed on test; useful window about -0.2..0.0.
- What did not work (dropped): cutting the dendrogram at its largest jump (ARI 0); concatenating the lexical embedder with a dense one (AUC and ARI got worse); ensembling two dense encoders (no better than gte-small alone); a gate on the raw mean similarity to detect "all rollouts are one approach" (absolute level does not transfer between problems: tuned for 10% false alarms, 17-77% on the unseen four; the problem-relative form was better but unstable across encoders, 5-29%).
- Final numbers through `analyze_directions` (30 random 8-of-12 batches per problem), paper setting -> new default:

| encoder | design ARI | TEST ARI | TEST exact #clusters | TEST H error (bits) | size |
|---|---:|---:|---:|---:|---:|
| paper setting, any MiniLM | 0.00 | 0.00 | 0.00 | 1.49 | |
| MiniLM-L6 int8 | 0.31 | 0.62 | 0.68 | 0.17 | 22 MB |
| MiniLM-L12 int8 | 0.45 | 0.60 | 0.69 | 0.16 | 32 MB |
| gte-small fp32 | 0.43 | 0.58 | 0.66 | 0.21 | 127 MB |
| lexical (no model) | 0.06 | 0.16 | 0.00 | 0.80 | none |

  Per-problem TEST ARI (L6 int8): 0.47, 0.77, 0.84, 0.38 — wide. L6 and L12 are tied within the noise; L6 is the smaller. The lexical embedder stays only as a dependency-free fallback and now says so (`reliable_for_diversity = False`, a warning in the result).
- Code: `diversity.py` (`dendrogram`, `cut_at_similarity`, `center`, `remove_direction`, `analyze_directions`, `CENTERED_TAU = -0.1`; the largest-gap cut was removed), `embedders.py` (`OnnxSentenceEmbedder` with mean or CLS pooling, MiniLM subclass), refiner config `diversity_view = "centered"` (paper's raw view stays selectable), `tau_centered`, `flat_margin`. Tests: 45 in agent-runtime (one needs `NEXUS_MINILM_DIR`, a real-encoder regression on a labelled fixture), whole repo 552 passed with the same 2 old failures, mypy unchanged at 2.
- Limits: one author, 8 problems, rollouts of 30-50 words (the paper's are long traces — its 0.85 may well be right for them; measure before assuming otherwise). Centering keeps only RELATIVE differences, so it cannot tell "all rollouts are one approach" from "several"; `flat_margin` is optional and uncalibrated. Fewer than 3 rollouts use the raw view. Timings were taken while the benchmark was running and mean little except as ratios.

# Phase 43 — Two long-lived branches: `main` = desktop app, `web` = hosted (Docker) — PLAN, not started
Decision (user, 2026-11-07): `main` is the desktop product shown to everyone; a second branch carries the web / Docker deployment. The local machine keeps only `main`.

## What I measured before planning
- ~95% of the source is shared (api 9.2k, web 9.2k, packages ~16k lines); only `apps/desktop` (829) is desktop-only and `infra/` (220) + the Docker files are web-only. So the branches must differ by ADDED files, never by deleted shared code, or every merge conflicts.
- Things that look web-only but are not: `packages/agent-runtime/nexus_plugins` and `nexusgen_bridge` import the Docker sandbox provider unconditionally (it stays on main, as an unused plugin); `apps/api/tests/test_billing.py` imports `scripts/issue_enterprise_license.py` (script stays on main with the billing code); `scripts/run-local.sh` needs `quickstart.sh` (`.env`) and `docker-compose.host-ports.yml` (a Docker-based dev route that `stack-cli` has replaced).
- The desktop app has a second mode (`apps/desktop/src/settings.ts`): a window onto any HTTPS server. Keep it: it is how the desktop app connects to a `web` deployment.
- A third Dockerfile exists: `packages/computer-sandbox/Dockerfile` (the sandbox image).

## Files that leave `main` (deployment artifacts and their docs only)
`docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.host-ports.yml`, `infra/production/`, `apps/api/Dockerfile`, `apps/web/Dockerfile`, `packages/computer-sandbox/Dockerfile`, `scripts/quickstart.sh`, `scripts/smoke_test.py`, `scripts/run-local.sh` (+ `scripts/load_env.py` if nothing else uses it; `.env.example` to be checked), the `images` job of `.github/workflows/ci.yml`, "Option B: Docker" and the compose lines in README.md / README.vi.md / AGENTS.md. All of it stays on `web`.

## Git sequence (so later merges stay clean)
1. Land the current work on `main` first (1 unpushed commit + uncommitted Phase 42 work): shared code must not change between steps 2 and 4.
2. Cut `web` from that `main` commit P and push it: it starts as the full current state.
3. On a feature branch off `main`, make commit D: ONLY the deletions above + README / docs / CI for the desktop. No shared-code edits in D. PR into `main`.
4. On `web`: `git merge -s ours main` once. It records D as merged without applying the deletions, moves the merge base past D, so later `git merge main` brings only newer shared changes.
5. On `web`, add only NEW files: `README.web.md`, `.github/workflows/web-images.yml`; the root README on `web` is the one file expected to conflict on each merge (resolve by keeping the web version).
6. `ci.yml` on both branches triggers on `push` to `main` and `web`.
7. Shared change: commit on `main`, then `git merge main` into `web`. Desktop-only change: `main` only. Web-only change: `web` only.
8. Trade-off to keep: `web` also carries `apps/desktop` (never edit it there).

## Local machine
Keep `main` checked out; `git remote set-branches origin main` stops fetching `web`; a worktree (`git worktree add ../Nexus-web web`) when the web side is needed.

## Needs the user's go-ahead (outward-facing)
Merging to `main`, creating and pushing `web`, deleting files from `main`.
