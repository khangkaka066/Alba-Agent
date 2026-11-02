# ROLE & OBJECTIVE

You are a Principal AI Systems Architect and Lead Full-Stack Engineer. Your task is to design and implement a 100% proprietary, production-grade, multi-tenant AI platform named **"NexusAgent Studio"** (replace with custom brand namespace where configured).

The platform unifies four foundational layers plus a **6-Pillar Proprietary Optimization & Governance Moat** into a single cohesive product owned 100% by us:

1. **Visual Workflow & BaaS Studio (Inspired by Dify concepts — Clean-Room):** Visual node-based workflow builder, multi-tenant RAG pipeline, unified LLM gateway, and instant REST API / WebApp publishing.
2. **Structured Multi-Agent Orchestration (Powered by CrewAI):** Deterministic state management via **CrewAI Flows** (`@start`, `@listen`, `@router`) and role-based SOP collaboration via **CrewAI Crews** (`Agent`, `Task`, `Crew`).
3. **Deep Problem Solving & Autonomous Code Execution (Powered by AutoGen):** Multi-turn conversational reasoning (`autogen-agentchat` / `autogen-core`) paired with isolated sandbox code execution (`autogen-ext`).
4. **Persistent AI Teammates, Computer Use & Human Governance (Adapted from Rakazo architecture):** Multi-platform persistent bots (Web, Desktop, Mobile, Voice Mode), scheduled Markdown routines, live graphical desktop/browser/terminal sandboxes (Local Docker, E2B, Daytona, CreateOS, Boat), and Human-in-the-Loop Approval Cards with full audit logging.
5. **6-Pillar Proprietary Moat (Our Unique Differentiators):**
   - **Pillar 1:** Governed Cross-Agent Learning Transfer, Propagation Scope Firewall & Negative Transfer Circuit Breaker.
   - **Pillar 2:** Self-Healing Prompt & Policy Optimizer from Human Approval Cards.
   - **Pillar 3:** Time-Travel Debugger & Live A/B Trajectory Forking.
   - **Pillar 4:** FinOps Auto-Distillation & Smart Model Arbitrage.
   - **Pillar 5:** Adversarial Swarm Consensus Mode.
   - **Pillar 6:** AI Meta-Architect & Conversational Team/Workflow Generator (Canvas Copilot).

# STRICT IP OWNERSHIP, CLEAN-ROOM & LICENSING GUARDRAILS (MANDATORY)

1. **100% Proprietary Ownership & Permissive License Allowlist:**
   - Every external dependency (across PyPI and npm, including transitive Next.js/React packages) MUST use a commercial-safe permissive license from this approved SPDX allowlist:
     `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `0BSD`, `ISC`, `Zlib`, `Unlicense`, `CC0-1.0`, `CC-BY-3.0`, `CC-BY-4.0`, `BlueOak-1.0.0`, `Python-2.0`, `Artistic-2.0`, and unmodified file-level `MPL-2.0`.
   - Strictly block restrictive copyleft or commercial-restricted licenses (`GPL-*`, `AGPL-*`, `SSPL-*`, `BUSL-*`, or Dify's modified license).
   - **DIFY (`./reference/dify` if present) — ZERO CODE COPYING:** Dify uses a restrictive modified license prohibiting multi-tenant SaaS and logo removal. You MUST NOT copy any Python, TypeScript, or React code verbatim from Dify. Use Dify strictly as a conceptual UX reference and write 100% original clean-room code.
2. **Complete White-Labeling & Brand Independence (`./reference/rakazo`, `./reference/crewAI`, `./reference/autogen`):**
   - When using or adapting permissive MIT/Apache-2.0 modules from Rakazo, CrewAI, or AutoGen:
     - Strip all external branding, product names (`Rakazo`, `Inbox Zero`, `Dify`, `LangGenius`, `CrewAI`, `AutoGen`), logos, and URI schemes from all user-facing UIs, API routes, CLI tools, and database tables.
     - Standardize all environment variables, package namespaces, and Docker images under our brand prefix (`NEXUS_*` / `@nexus/*`).
     - Maintain a single consolidated `THIRD_PARTY_NOTICES.md` file in the repository root preserving required permissive copyright attributions for third-party dependencies.
3. **Zero External Telemetry (Privacy & Security by Default):**
   - Hardcode `OTEL_SDK_DISABLED=true`, `CREWAI_DISABLE_TELEMETRY=true`, and strip any outbound analytics/telemetry beacons so zero usage data ever leaves our infrastructure.
4. **First-Class Multi-Tenancy & Row-Level Security (RLS):**
   - Every PostgreSQL table, Qdrant vector payload, Redis pub/sub channel, sandbox container, knowledge capsule, and LiteLLM spend log MUST enforce strict isolation by `tenant_id` and `workspace_id`.

# TARGET MONOREPO STRUCTURE

Maintain the following clean monorepo layout:

```text
nexus-agent-studio/
├── AGENTS.md                          # Master architecture, IP rules & coding conventions
├── THIRD_PARTY_NOTICES.md             # Consolidated permissive license attributions
├── docker-compose.yml                 # Unified stack: postgres, redis, qdrant, sandbox-supervisor, worker, api, web
├── docker-compose.prod.yml            # Production stack with HTTPS proxy, healthchecks & resource limits
├── .env.example
├── packages/
│   ├── core-schema/                   # Shared Pydantic v2 & TypeScript/Zod schemas (Flows, Crews, AutoGen, Bots, Approvals, Capsules)
│   │   └── templates/                 # Seed Vertical Agent Blueprints (Data Science, QA Auditor, Market Research, Ops Bot)
│   ├── agent-runtime/                 # Dual-Engine Orchestrator & Proprietary Runtime Capabilities
│   │   ├── nexus_kernel/              # Plugin kernel: scoped context (`ctx`), typed service keys, 5 event modes, plugin lifecycle, YAML rows + patches
│   │   ├── nexus_plugins/             # Runtime capabilities as plugins (infrastructure, llm, sandbox, tools, checkpoints) + `default.yaml`
│   │   ├── flows/                     # Dynamic Flow compiler & Pydantic state manager
│   │   ├── crews/                     # CrewAI builder from bi-directional JSONC/YAML configs
│   │   ├── autogen_bridge/            # AutoGen GroupChat + Shared Sandbox Code/Browser Executor wrapper
│   │   ├── architect/                 # Pillar 6: AI Meta-Architect & Conversational Team/Workflow Generator
│   │   ├── time_travel/               # Pillar 3: Time-Travel Checkpoint Rewind & A/B Trajectory Forking
│   │   ├── consensus/                 # Pillar 5: Adversarial Swarm Consensus & Arbiter Judge
│   │   ├── callbacks/                 # Real-time event emitter to Redis Pub/Sub (thoughts, tool calls, terminal, approvals)
│   │   └── checkpoints/               # Postgres/Redis state persistence for pause/resume & human approval gates
│   ├── learning-transfer/             # Pillar 1 & 2: Cross-Agent Learning Transfer, Scope Firewall, Negative Transfer & Self-Healing
│   │   ├── distiller.py               # Extracts KnowledgeCapsules from AutoGen debug loops & human edits
│   │   ├── scope_firewall.py          # Epistemic graph boundary enforcement & PII/secret redaction
│   │   ├── negative_transfer_detector.py # Transfer Impact Score (TIS) telemetry & automatic circuit breaker
│   │   └── self_healing.py            # Pillar 2: Generates git-diff PromptPatchProposals from Approval Card edits
│   ├── computer-sandbox/              # Persistent Computer & Live Screen Supervisor (Docker, E2B, Daytona, CreateOS, Boat)
│   ├── rag-engine/                    # Multi-tenant LlamaIndex + Qdrant ingestion & hybrid retrieval
│   ├── model-gateway/                 # LiteLLM router, BYOK, cost tracking & Pillar 4 FinOps Auto-Distillation (`auto_distill.py`)
│   └── mcp-hub/                       # Unified Model Context Protocol & OpenAPI client for CrewAI, AutoGen & Persistent Bots
├── apps/
│   ├── api/                           # FastAPI Control Plane, BaaS REST API, SSE/WebSocket Streaming & Async Workers
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── auth/                  # Multi-tenant JWT, Row-Level Security (RLS), RBAC, Service API Keys (nx-sk-...), Ed25519 License Verifier
│   │   │   ├── billing/               # Subscription tiers (FREE, PRO, ENTERPRISE), quota guards & payment webhooks
│   │   │   ├── models/                # SQLAlchemy 2.0 async models (Tenants, Workspaces, Bots, Routines, Workflows, Capsules, Approvals, AuditLogs, Usage)
│   │   │   ├── routers/               # /v1/workflows, /v1/architect, /v1/bots, /v1/runs, /v1/learning-transfer, /v1/self-healing, /v1/approvals, /v1/sandboxes, /v1/knowledge-bases, /v1/templates, /v1/analytics
│   │   │   └── workers/               # Async background workers for Flows, scheduled Markdown routines & shadow distillation jobs
│   │   └── tests/
│   ├── web/                           # Next.js 15 / React 19 + TypeScript + Tailwind + @xyflow/react
│   │   ├── src/
│   │   │   ├── app/                   # Workspace Dashboard, Persistent Bot Chat/Voice, Visual Workflow Studio, Template Gallery, Learning Transfer Radar, FinOps
│   │   │   ├── components/canvas/     # React Flow nodes (Trigger, Crew, AutoGenSandbox, ApprovalGate, Router, RAG) + ArchitectCopilot + Dashed Learning Edges
│   │   │   ├── components/teammates/  # Persistent Bot profile, Markdown Routine scheduler, Bidirectional Voice UI, Approval Cards + Prompt Diff Modal
│   │   │   ├── components/inspector/  # Live SSE trace drawer, Time-Travel & A/B Forking Timeline, Live Virtual Desktop Screen & Terminal stream
│   │   │   └── lib/                   # Typed API client, SSE & WebSocket audio/terminal stream hooks
│   ├── desktop/                       # Optional Electron shell connecting to local Docker stack or remote HTTPS server
│   └── mobile/                        # Optional Expo (iOS/Android) client for chatting, voice calls & approving actions on the go
```

# CORE TECHNICAL SPECIFICATIONS TO IMPLEMENT

## 1. Dual-Engine Runtime (`packages/agent-runtime`)
- **Dynamic Flow Compiler (`flows/compiler.py`):**
  - Accepts a validated `WorkflowSpec` Pydantic object (serialized from the React Flow visual canvas or Git JSONC/YAML files).
  - Dynamically constructs an executable `crewai.flow.flow.Flow` subclass holding a typed `WorkflowState(BaseModel)`.
  - Wires `@start()`, `@listen()`, and `@router()` methods according to graph edges, persisting a `RunCheckpoint` after each step.
- **AutoGen Sandbox Bridge (`autogen_bridge/sandbox_team.py`):**
  - Implements `AutoGenCodeExecutionTool(BaseTool)` for CrewAI agents AND a standalone async runner for Flow nodes.
  - Uses `autogen_agentchat.agents.AssistantAgent` (`CoderAgent` & `ReviewerAgent`) connected to our unified `packages/computer-sandbox` supervisor.
  - Runs an iterative multi-turn verification loop (`RoundRobinGroupChat` or `SelectorGroupChat`) until generated code executes cleanly (exit code 0) and passes verification.
  - Streams all intermediate code blocks, terminal stdout/stderr, and desktop screen frames to `RuntimeEventEmitter`, returning a concise `SandboxResult(summary, artifacts, exit_code, metrics)` back to CrewAI.
- **Real-Time Event Bus (`callbacks/event_bus.py`):**
  - Publishes structured JSON events to Redis channel `run:{tenant_id}:{run_id}:events`:
    - `FLOW_STATE_CHANGED`, `CREW_AGENT_THOUGHT`, `TOOL_INVOKED`
    - `AUTOGEN_CODE_GENERATED`, `SANDBOX_TERMINAL_OUTPUT`, `SANDBOX_SCREEN_FRAME`
    - `APPROVAL_REQUIRED`, `APPROVAL_RESOLVED`, `NEGATIVE_TRANSFER_DETECTED`, `RUN_COMPLETED`, `RUN_FAILED`

## 2. Persistent AI Teammates, Computer Sandbox & Approval Gates (`packages/computer-sandbox` & `apps/api`)
- **Persistent Teammate Bots & Bidirectional Voice:**
  - Each Bot has persistent memory, conversation threads, assigned LLM model, connected MCP/OpenAPI tools, **Markdown Routines**, and bidirectional WebSocket Voice streaming (`/api/v1/bots/{bot_id}/voice/stream` with STT/TTS).
  - Any Bot can trigger a multi-agent **CrewAI + AutoGen Workflow** via the internal MCP/Tool bridge or delegate subtasks to peer bots.
- **Unified Computer Sandbox Supervisor (Hardened):**
  - Supports **Shared Team Computers** and **Isolated Private Computers** with browser, shell/terminal, file system, and graphical desktop access (`SCREEN_PROXY`).
  - Pluggable providers: local `docker` (default, enforcing `cap_drop=["ALL"]`, `no-new-privileges:true`, CPU/RAM limits, and private metadata IP blocking) plus cloud providers (`e2b`, `daytona`, `createos`, `boat`, `railway`).
- **Human-in-the-Loop Approval Cards & Immutable Audit Log:**
  - When a Flow reaches an `ApprovalGateNode`, falls below Swarm Consensus threshold, or attempts a boundary-crossing action, execution checkpoints its state and pauses.
  - Emits an `APPROVAL_REQUIRED` event rendering an interactive **Approval Card** (`Allow once` / `Always allow in this routine` / `Deny`) with every decision recorded in `audit_logs`.

## 3. Multi-Tenant RAG & Unified MCP Hub (`packages/rag-engine` & `packages/mcp-hub`)
- **Multi-Tenant Qdrant Vector Store:**
  - Enforces mandatory payload filtering on `tenant_id` and `knowledge_base_id` on every query (`Filter(must=[...])`) to guarantee zero cross-tenant data leakage.
  - Supports PDF, DOCX, Markdown, CSV parsing, semantic chunking, and hybrid search via LlamaIndex.
- **Unified MCP & OpenAPI Adapter:**
  - Connects to HTTPS/stdio MCP servers and OpenAPI 3.1 specs, exposing tools simultaneously to Persistent Bots, CrewAI Agents, and AutoGen `McpWorkbench`.

## 4. 6-Pillar Proprietary Moat (`packages/learning-transfer`, `packages/agent-runtime`, `packages/model-gateway`)
- **Pillar 1 — Governed Cross-Agent Learning Transfer & Negative Transfer Circuit Breaker (`packages/learning-transfer`):**
  - Distills reusable `KnowledgeCapsule` units from successful AutoGen multi-turn debugging and human corrections.
  - Enforces an **Epistemic Propagation Scope Firewall** (`AGENT_PRIVATE`, `CREW_LOCAL`, `WORKFLOW_SCOPED`, `WORKSPACE_QUARANTINE`, `WORKSPACE_VERIFIED`) with automatic PII/secret redaction.
  - Continuously computes the **Transfer Impact Score ($\text{TIS}_{k \to B} \in [-1.0, +1.0]$)**:
    $$\text{TIS}_{k \to B} = w_1 \Delta \text{SuccessRate} - w_2 \Delta \text{RetryRate} - w_3 \Delta \text{RejectionRate} - w_4 \Delta \text{TokenOverhead}$$
  - Automatically quarantines/revokes any capsule causing **Negative Transfer** ($\text{TIS}_{k \to B} < -\theta$) and logs the blocked domain pair.
- **Pillar 2 — Self-Healing Prompt & Policy Optimizer (`packages/learning-transfer/self_healing.py`):**
  - Computes structural/semantic diffs whenever a human edits an agent's output or rejects an `ApprovalCard` with feedback.
  - Generates a Git-style **`PromptPatchProposal`** for one-click prompt/guardrail patching AND mints a verified `KnowledgeCapsule`.
- **Pillar 3 — Time-Travel Debugger & Live Trajectory Forking (`packages/agent-runtime/time_travel/`):**
  - Allows selecting any historical `RunCheckpoint` on the canvas, mutating state variables or prompts inline, and executing **Rewind & Resume** or **A/B Trajectory Forking** (running 2 parallel branches from step $N$ and comparing output diffs, latency, and cost).
- **Pillar 4 — FinOps Auto-Distillation & Smart Model Arbitrage (`packages/model-gateway/auto_distill.py`):**
  - Collects verified `GoldenTraces` from frontier models and runs background shadow evaluations on cheaper/local candidate models augmented with dynamic golden few-shot examples.
  - Surfaces a one-click **"Auto-Downgrade & Save X%"** recommendation when schema and semantic parity $\ge 95\%$.
- **Pillar 5 — Adversarial Swarm Consensus Mode (`packages/agent-runtime/consensus/`):**
  - Executes high-stakes nodes concurrently across $\ge 2$ heterogeneous model families with 1-round AutoGen cross-critique and an `ArbiterJudge` scoring `consensus_confidence`. Automatically routes to an `ApprovalGateNode` if confidence is below threshold.
- **Pillar 6 — AI Meta-Architect & Conversational Team Generator (`packages/agent-runtime/architect/`):**
  - Synthesizes a complete, compilable `WorkflowSpec` (with `CrewNode`, `AutoGenSandboxNode`, `ApprovalGateNode`, bound MCP/RAG tools, pre-attached high-TIS `KnowledgeCapsules`, and auto-layout coordinates) from a natural language requirement prompt, and supports conversational graph editing (**Canvas Copilot**).

# PLUGIN ARCHITECTURE: "EVERYTHING IS A PLUGIN" (`nexus_kernel` + `nexus_plugins`)

The process is assembled at boot from a list of plugins instead of being wired by hand. The design borrows the container pattern used by Cordis-style plugin frameworks; the code is an original Python implementation.

- **Kernel (`packages/agent-runtime/nexus_kernel/`)** is deliberately empty of business logic and imports only the standard library and `yaml` (a test enforces it). It provides:
  - `Context` (`ctx`): a scope that holds services. Child scopes (for example one per workspace or run) see their parents' services but never a sibling's. Services are looked up by a typed `ServiceKey`, never by importing an implementation.
  - **Reversible registrations.** Services, listeners and `ctx.on_dispose(...)` effects registered by a plugin are removed, newest first, when it stops. A failing disposer is collected and never blocks the others.
  - **Events** in five modes: `emit`, `parallel`, `serial`, `bail` and `waterfall` (middleware around a core call; a listener may short-circuit). `ctx.declare_event` pins a mode so producers and consumers cannot disagree.
  - **Plugin lifecycle**: `pending` (a required service is missing) → `loading` → `active` → `disposing` → `stopped`/`failed`. A plugin waits for what it `requires`, stops when that service disappears, restarts when an `optional` service appears or goes, and a failed `apply` is rolled back completely.
  - **Configuration**: ordered rows `{id, plugin, config, disabled}` from `default.yaml`, layered with patch files (a patch replaces a row's whole `config`, can disable, insert or remove rows). Rows name registered plugins only, never import paths. `Kernel.reconfigure(rows)` applies a changed list touching only what differs.
- **Plugins (`packages/agent-runtime/nexus_plugins/`)** publish services through the keys in `seams.py`:

  | Plugin (`plugin:` name) | Provides | Requires |
  |---|---|---|
  | `infrastructure.runtime` | `DATABASE`, `REDIS`, `QDRANT` (opened on start, closed on stop) | none |
  | `llm.gateway` | `LLM` (credential resolution, routers, CrewAI and AutoGen clients) | `DATABASE` |
  | `memory.checkpoints` | `CHECKPOINTS` (append-only run state for pause, resume and time-travel) | `DATABASE`, `REDIS` |
  | `tools.registry` | `TOOLS` (per-run built-in registries, tools mounted per workspace) | none |
  | `sandbox.supervisor` | `SANDBOX` (a supervisor with no provider of its own) | `DATABASE` |
  | `sandbox.docker` | registers the Docker provider on `SANDBOX` | `SANDBOX` |
  | `sandbox.runner` | `SANDBOX_RUNNER` (AutoGen coder and reviewer team) | `DATABASE`, `LLM`, `SANDBOX`, `TOOLS` |

- **Rules**
  1. A plugin module imports the kernel, `nexus_plugins.seams`, `nexus_plugins.support.*` and domain packages. It must **not** import another plugin module or `app.services`; collaboration goes through `ctx` (`tests/test_phase22_plugins.py` checks this with an AST scan).
  2. Anything a plugin adds (prompt sections, tools, listeners, providers) is registered through `ctx` so it disappears with the plugin. Never keep a registration outside a disposer.
  3. Plugin scope is not tenant isolation. Per-tenant data still goes through `scoped_session` and RLS.
  4. A new capability is a new plugin plus a key in `seams.py`; add it to `default.yaml` and to `default_registry()`.
- **Operating it**: `python -m nexus_plugins dump-config [--patch file.yaml ...]` prints the list a process would boot. `NEXUS_PLUGINS_FILE` replaces the base list and `NEXUS_PLUGIN_PATCHES` (comma separated) layers patches. `create_default_services()` boots the list; `AppServices.shutdown()` closes it. `AppServices` keeps its previous public surface.
- **Not yet plugins**: the workflow compiler's node handlers (`flows/compiler.py`), learning-transfer capsule injection, and cross-process reload of the plugin list. These are the next steps.

# CODING STANDARDS & VERIFICATION COMMANDS

- **Strict Typing & Production Quality:** Python 3.11+ with `pydantic` v2 and `mypy --strict`; TypeScript 5+ with `strict: true`. Never leave `pass`, `TODO`, bootstrap placeholders, or mock stubs in orchestration, database, Docker Compose, or sandbox bridges.
- **Automated Verification Before Completing Any Task:**
  1. Run backend lint, typechecks & unit/integration tests: `pytest` and `mypy packages/ apps/api/`
  2. Run frontend typechecks & tests: `pnpm lint && pnpm check && pnpm test`
  3. Run full-stack E2E smoke test: `python3 scripts/smoke_test.py`
  4. Run IP & Branding Hygiene Check:
     ```bash
     # Must return 0 matches in user-facing code and configs:
     grep -riE "langgenius|dify|rakazo|inbox zero" apps/ packages/ --exclude="THIRD_PARTY_NOTICES.md"
     ```
