<p align="center">
  <picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/alba-logo-dark.svg"><img src="docs/assets/alba-logo.svg" alt="Alba Agent" width="180"></picture>
</p>

<h3 align="center">A governed team of AI agents in your own sandbox.<br>Describe a goal. Agents plan, code and produce files. You approve the risky steps.</h3>

<p align="center">
  <a href="https://github.com/khangkaka066/Alba-Agent/actions/workflows/ci.yml"><img src="https://github.com/khangkaka066/Alba-Agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/khangkaka066/Alba-Agent?color=2f6fed" alt="MIT license"></a>
  <a href="https://github.com/khangkaka066/Alba-Agent/stargazers"><img src="https://img.shields.io/github/stars/khangkaka066/Alba-Agent?style=flat&logo=github&color=2f6fed" alt="Stars"></a>
  <a href="https://github.com/khangkaka066/Alba-Agent/forks"><img src="https://img.shields.io/github/forks/khangkaka066/Alba-Agent?style=flat&logo=github&color=2f6fed" alt="Forks"></a>
  <a href="https://github.com/khangkaka066/Alba-Agent/issues"><img src="https://img.shields.io/github/issues/khangkaka066/Alba-Agent?style=flat&color=2f6fed" alt="Issues"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-welcome-2f6fed?style=flat" alt="PRs welcome"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-2f6fed?style=flat&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/FastAPI-2f6fed?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Next.js-15-2f6fed?style=flat&logo=next.js&logoColor=white" alt="Next.js 15">
  <img src="https://img.shields.io/badge/PostgreSQL-RLS-2f6fed?style=flat&logo=postgresql&logoColor=white" alt="PostgreSQL with row-level security">
  <img src="https://img.shields.io/badge/macOS-no%20Docker-2f6fed?style=flat&logo=apple&logoColor=white" alt="Runs on macOS without Docker">
  <img src="https://img.shields.io/badge/MCP-ready-2f6fed?style=flat" alt="MCP">
</p>

<p align="center">
  <a href="#-install">Install</a> ·
  <a href="#-see-it">Screenshots</a> ·
  <a href="#-the-interface">Interface</a> ·
  <a href="#-what-you-get">Features</a> ·
  <a href="#-agent-studios">Agent studios</a> ·
  <a href="#-connect-a-model">Models</a> ·
  <a href="#-roadmap-and-honest-limits">Roadmap</a> ·
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

---

## Why Alba Agent

Most multi-agent projects are libraries: you write the orchestration, the sandbox, the review step and the UI yourself. Alba Agent is the finished product built on top of them. It is a self-hosted web and desktop app where you type a goal, an AI architect designs a whole **team** of agents for it, the team runs inside an isolated sandbox, and a human approves the sensitive steps.

- **Team, not chatbot.** A request becomes a structured team: directors, department leads and specialists, with a quality gate that sends missing work back to the right department.
- **Runs on your Mac without Docker.** The desktop app carries its own database, queue, vector store, API, Node, git and ffmpeg; agent commands run in an operating-system sandbox. A server version that runs in Docker is kept on the [`docker` branch](https://github.com/khangkaka066/Alba-Agent/tree/docker).
- **Safe by design.** Code runs in a locked-down sandbox. Sensitive actions stop at an approval card. Every decision is written to an audit log.
- **Honest results.** A team that claims a file it never wrote fails with a clear message (media is never invented) instead of finishing as if it had delivered.
- **Bring any model.** Use your ChatGPT, Claude or Gemini plan, an API key, any OpenAI-compatible gateway, or a local Ollama model.
- **Yours.** Self-hosted, MIT licensed, no telemetry leaves your machine.

---

## 🖼️ See it

<p align="center"><img src="docs/screenshots/alba-home.png" alt="Alba Agent with separate Model and Effort controls" width="960"></p>

The current interface uses the ALBA master emblem. Model and Effort are separate controls; account sign-in lives in Settings → Models. The agent-team canvas remains available beside the conversation.

<details><summary>Agent-team canvas</summary>
<p align="center"><img src="docs/screenshots/alba-canvas.png" alt="Alba Agent hierarchical team canvas" width="960"></p>
</details>

---

## 🧭 The interface

The window follows the layout of modern AI code editors, so what matters is in front of you and the rest is one key away.

| Area | What it holds |
|---|---|
| **Title bar** | Sidebar toggle, back and forward, search; the breadcrumb `Project / Conversation`; a menu (copy the conversation, run log, shortcuts), the *Overview* menu and the right-panel toggle. |
| **Sidebar** | *New Conversation*, *Automations* (scheduled teammates), *Customizations* (channels, MCP, skills); **Projects** (a folder you opened, with its conversations); **Conversations**; *Settings* and your account at the foot. |
| **Conversation** | Messages, the team's live progress, approval cards, and the message box: attach (`+` or `@`), Model, Effort, permissions, dictation (browsers that support it), send. |
| **Right panel** | *Review* (lines added and removed), *Files* (diff, download, accept), an interactive *Terminal*, *Browser*, *Canvas* (the agent graph and the run log). Drag its edge to resize, or expand it to full width. |
| **Settings** | A panel over the work: General, Application, Appearance, Shortcuts, Notifications and Models. |

| Keys | Action |
|---|---|
| `⌘⇧P` / `Ctrl+Shift+P` | Command palette |
| `⌘Enter` | Send the message |
| `⌘L` | Focus the message box |
| `⌘J` | Show or hide the right panel |
| `⌘I` | Open the agent run log (Canvas) |
| `⌘B` | Show or hide the sidebar |
| `⌘\` | Toggle the agent canvas |
| `A` / `Y` / `D` | On the first approval card: allow once / always allow (scheduled tasks) / deny |

Shortcuts can be changed in **Settings → Shortcuts**. On narrow windows the sidebar becomes a drawer and the right panel covers the conversation.

---

## ⚡ Install

You need either an AI subscription you already use (ChatGPT, Claude, Gemini) or an API key.

### The desktop app (macOS, Apple Silicon, no Docker)

The installer carries the whole product: PostgreSQL, Redis, Qdrant, the API, the worker and the web app start inside the app. Agent commands find Node 22, git and ffmpeg inside the app too, so nothing has to be installed on the Mac.

```bash
python3 scripts/package/build_runtime.py mac-arm64     # downloads (sha256-pinned) and assembles the runtime
python3 scripts/package/verify_runtime.py mac-arm64    # portability audit and a smoke run from a relocated copy; must pass
pnpm --filter @nexus/desktop build:mac                 # apps/desktop/release/Alba Agent-<version>-mac-arm64.dmg
```

Open the `.dmg` and drag Alba Agent to Applications. Requirements and limits, stated plainly:

- **macOS 15 or later on Apple Silicon.** There is no Intel or Windows installer yet.
- **The `.dmg` is not signed or notarized**, so macOS asks you to confirm the first launch (right-click the app, then *Open*).
- **No browser is bundled.** The `headless-browser` command used by agents needs Chrome, Chromium, Edge or Brave to be installed, and says so when none is found.
- There is no published download yet; build it with the three commands above.

Details: [apps/desktop/README.md](apps/desktop/README.md).

### Server, Linux and Windows

There is no installer for them on `main`. A Docker deployment (any OS with Docker, and self-hosted servers with HTTPS) is kept on the [`docker` branch](https://github.com/khangkaka066/Alba-Agent/tree/docker); a Windows build is planned and has not been started. The desktop app can also open a window onto a server you run from that branch (*Settings* in the app, an HTTPS address).

## First run

Open the app. There is no sign-up: a *Local Workspace* is created for you. Then:

1. **Settings → Models:** connect a model (see [Connect a model](#-connect-a-model)).
2. Type what you want and press Enter.
3. Open the files the team produced in the right panel, review them, accept or download them, or hand them to another team.

---

## ✨ What you get

| | Feature | What it does |
|---|---|---|
| 🧠 | **AI Meta-Architect** | Turns a sentence into a compilable team: agents, tasks, tools, knowledge and approval gates. |
| 🏢 | **Hierarchical teams** | Directors, department leads and specialists work in parallel waves with artifact contracts and a rework loop. |
| 💻 | **Code sandbox** | Coder and reviewer agents run code until it verifies: in the macOS app, in an operating-system sandbox with a command policy (deny, ask, allow). The Docker branch runs the code in containers instead (no network, dropped capabilities, resource limits). |
| ✅ | **Human approval** | Sensitive steps pause on an *Allow once / Always allow / Deny* card; every decision is audited. |
| 🗂️ | **Task history** | Every task and its conversation is saved; reopen it, delete it, or retry it. |
| 🩺 | **Readable failures** | The failure card names the department and agent that stopped and the sanitised error. Retry only the failed step (finished departments are kept) or the whole team. |
| 🔗 | **Team-to-team handoff** | Attach files from an earlier task with `@`, or press *Hand off* to start a marketing or analytics team from the results. |
| 🔌 | **Model freedom** | Subscription connectors, API keys, OpenRouter, Groq, Mistral, DeepSeek, Ollama, LM Studio, vLLM and any OpenAI-compatible gateway; switch model per task. |
| 📚 | **RAG + MCP** | Upload documents into a knowledge base (Qdrant), or connect MCP servers and OpenAPI tools. |
| 🔁 | **Time travel** | Rewind to any checkpoint, edit state, resume, or fork two branches and compare them. |
| 🧬 | **Learning & evolution** | Agents share vetted lessons under a scope firewall; teams diagnose bottlenecks and propose new generations, with rollback. |
| 💸 | **FinOps** | Per-model cost tracking, plan usage recorded at $0, and cheaper-model suggestions once quality is verified. |
| 🛡️ | **Multi-tenant security** | PostgreSQL row-level security on every table, RBAC, scoped API keys, encrypted credentials. |
| 🌐 | **English and Vietnamese** | Switch the interface language at any time. |

---

## 🎬 Agent studios

Ask for a product and Alba Agent builds a whole studio. Pick the size: *compact*, *by department* (~19 agents) or *full studio*.

| Studio | Agents | Produces |
|---|---:|---|
| **Feature Film & Series Production** | 50 | Screenplay, storyboard and previs, design and casting, camera, sound, VFX, budget and schedule, animatic, distribution plan. |
| **Full Game Development** | 49 | Design docs, art direction, code, build checks, playable preview. |
| **Marketing & Social Publishing** | 41 | Strategy, copy, per-channel packages for TikTok, YouTube and Facebook, content calendar, KPI tracker, launch checklist. |
| **Analytics & Optimization** | 34 | Measurement plan, KPI baseline from the data you attach, experiment plan, forecast, HTML report. |
| **Full-Stack SaaS & AI Software Factory** | 32 | Architecture, backend and frontend code, tests, security review, release notes. |
| **Cinematic Video & Documentary** | 26 | Research, script, storyboard, voice and sound plan, subtitles, contact sheet. |

Plus four small templates: Data Science & Financial Analyst, Software QA & Security Auditor, Market Research & Content Engine, and an Executive Inbox & Operations teammate.

---

## 🏗️ How it works

```mermaid
flowchart LR
    U([You]) -->|goal| A[Meta-Architect]
    A -->|designs| T[Agent team]
    T --> D1[Department crews]
    T --> D2[Sandbox teams]
    D1 --> Q{Quality gate}
    D2 --> Q
    Q -->|missing files| D1
    Q -->|pass| H{{Human approval}}
    H -->|approved| R[Files and report]
    R -->|hand off| T2[Next team]
```

```mermaid
flowchart TB
    Web["Web app (Next.js 15) and Desktop (Electron)"] --> API["API (FastAPI)"]
    API --> PG[("PostgreSQL + RLS")]
    API --> RD[("Redis: events")]
    API --> WK["Worker (Celery)"]
    WK --> RT["Runtime: NexusAI Flows + NexusGen"]
    RT --> SB["OS sandbox (macOS)"]
    RT --> QD[("Qdrant: RAG")]
    RT --> GW["Model gateway (LiteLLM)"]
```

The runtime is assembled from plugins: connections, model access, checkpoints, tools, and the sandbox supervisor with its providers (local macOS, Docker, cloud) are independent plugins mounted by a small kernel (`python -m nexus_plugins dump-config` prints what a process boots). See [AGENTS.md](AGENTS.md) for the rules.

| Path | Role |
|---|---|
| `apps/web` | Next.js interface |
| `apps/api` | FastAPI control plane, auth, billing, workers |
| `apps/desktop` | Electron shell with local folder mounting |
| `packages/agent-runtime` | Flow compiler, crews, NexusGen bridge, time travel, consensus, plugin kernel |
| `packages/learning-transfer` | Knowledge capsules, scope firewall, self-healing prompts |
| `packages/model-gateway` | Providers, subscription connectors, pricing, FinOps |
| `packages/computer-sandbox` | Local (macOS), Docker and cloud sandbox providers |
| `packages/rag-engine`, `mcp-hub`, `builtin-tools` | Retrieval, MCP and OpenAPI tools, built-in tools |
| `packages/core-schema` | Shared schemas and the studio blueprints |

---

## 🔌 Connect a model

Open **Settings → Models**.

| Source | Connection |
|---|---|
| **Codex / ChatGPT** | Install the official Codex CLI, then choose **Sign in with Codex**. Complete the browser flow; Alba verifies a real answer before enabling the connection. |
| **Claude Pro / Max** | Install the official Claude Code app and choose **Sign in with Claude**. The official app owns your login and plan limits. |
| **Google / Gemini** | Sign in through the official Antigravity ACP runtime. Retired Gemini CLI personal Code Assist authentication is not used. |
| **API providers** | Enter the provider URL and API key in Models. Saved credentials are encrypted and scoped to your workspace. |
| **Local models** | Connect an Ollama or other supported local server. |

Sign-in runs through each provider's unmodified official application. Alba does not ask you to paste subscription tokens or credential files. Official account programs are installed separately and are not redistributed as dependencies of Alba. Connecting a subscription does not overwrite saved API provider credentials. An authenticated account that returns 429 is shown as **Signed in · Limited**, without replacing another working model.

The chat has separate **Model** and **Effort** controls. Codex models and reasoning levels are discovered through its official app-server; Gemini options come from the official Antigravity ACP catalog. Model families appear once; Effort lists only the levels the account actually supplies. Unsupported effort controls are disabled. The selected concrete model and effort survive reloads. Availability and usage limits are controlled by the provider; zero metered API cost does not imply unlimited subscription usage.


---

## 🖥️ Desktop app

[apps/desktop](apps/desktop/README.md) is an Electron shell around the same interface. Besides the self-contained install above it adds: open a real project folder (`⌘/Ctrl+O`) that appears under **Projects**, review changes as diffs and accept them into your files, a global shortcut (`⌘/Ctrl+Shift+Space`) for quick tasks, and system notifications. `pnpm --filter @nexus/desktop dev` runs it from source. Only the macOS Apple Silicon `.dmg` has been built and verified; the Windows and Linux targets are configured but untested, and the Windows build would still need a sandbox and a verifier of its own.

---

## ⚙️ Configuration

| Group | Variables |
|---|---|
| Security | `NEXUS_SECRET_KEY`, `NEXUS_API_KEY_PEPPER`, `NEXUS_CREDENTIAL_ENCRYPTION_KEY_BASE64` |
| Models | `NEXUS_*_API_KEY` (optional server keys), `NEXUS_MODEL_RATES_JSON` (optional cost estimates) |
| Official account apps | `NEXUS_ACCOUNT_CLI_DIR`, `NEXUS_ACCOUNT_CODEX_BIN`, `NEXUS_ACCOUNT_CLAUDE_BIN`, `NEXUS_ACCOUNT_GEMINI_BIN` |
| Plugins | `NEXUS_PLUGINS_FILE`, `NEXUS_PLUGIN_PATCHES` |
| Access | `NEXUS_LOCAL_MODE`, `NEXUS_PUBLIC_SIGNUP_ENABLED`, `NEXUS_REGISTRATION_TOKEN`, `NEXUS_CORS_ORIGINS` |
| Sandbox | `NEXUS_COMPUTER_ROOT`, `NEXUS_SANDBOX_PROVIDER` |

Everything is listed in [.env.example](.env.example). Call the API with a scoped key: `curl -H "Authorization: Bearer nx-sk-<KEY>" http://localhost:8000/api/v1/workflows`.

---

## 🧪 Development and tests

```bash
pytest && mypy packages/ apps/api/          # backend tests and strict typing
pnpm lint && pnpm check && pnpm test        # frontend
```

CI runs the same commands plus licence and branding checks on every push. Current local results and test limitations are recorded in [the Alba rollout verification](docs/verification/alba-rollout/README.md). Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

---

## 🧭 Roadmap and honest limits

- **Posting to TikTok, Facebook and YouTube is not wired yet.** The marketing and film teams write publish-ready packages and checklists and stop at your approval; channel cards store a token and check connectivity only.
- **Video generation** depends on your provider offering a video API. Agents describe, plan and assemble media; they do not invent files.
- The interface has a single local workspace for now; the multi-workspace switcher is planned (the backend already isolates workspaces).
- **Browser and terminal access depend on the sandbox provider.** The local macOS provider supports interactive terminals, managed background processes and a remote browser screen. Browser checks use the assigned sandbox browser. Dictation needs a browser with speech recognition.
- The new shell is dark-first; the light theme is not fully restyled yet.
- With an unusual model gateway the architect may pick model names the gateway does not have (the task then stops with a *model not found* error). Choose a model you have connected, or give the full provider-qualified id.
- Agents can still misjudge their own work. Failed claims are caught and reported, and every run can be retried, but review important output yourself.
- Planned: node handlers as plugins, per-workspace plugin configuration, Windows and Linux desktop verification.

Ideas and bug reports are welcome in [Issues](https://github.com/khangkaka066/Alba-Agent/issues).

---

## ⭐ Support the project

If Alba Agent saves you time, a star helps other people find it, and sharing a screenshot of a team you built helps even more.

<a href="https://star-history.com/#khangkaka066/Alba-Agent&Date">
  <img src="https://api.star-history.com/svg?repos=khangkaka066/Alba-Agent&type=Date" alt="Star history" width="520">
</a>

## 🔒 Security and license

- Isolation by tenant and workspace in PostgreSQL, Qdrant, Redis and the sandbox. Report vulnerabilities privately: see [SECURITY.md](SECURITY.md).
- No telemetry is sent anywhere.
- Only permissively licensed dependencies are used (checked in CI); see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Released under the [MIT License](LICENSE).

<sub>**Topics:** multi-agent, ai-agents, agent-orchestration, llm, workflow-automation, mcp, rag, human-in-the-loop, desktop-app, macos, fastapi, nextjs, multi-tenant, ai-workflow-builder.</sub>

## Brand and compatibility

The application is now **Alba Agent**, using the owner-supplied ALBA master logo. The repository retains the `@nexus/*` package scopes, `NEXUS_*` environment variables, database identifiers and existing local data directories for compatibility with earlier installs. This does not reset saved accounts, API keys or conversations. Product text, app metadata, launch screen and icons use the Alba identity.

In **Auto** mode, clear website creation briefs and their technology follow-ups are routed into workflow/team generation. Greetings and questions remain ordinary chat; asking for a plan or advice does not start execution.
