# Agent runtime

The runtime compiles validated workflow graphs into native asynchronous Flow subclasses. Each completed node writes a PostgreSQL checkpoint and refreshes a scoped Redis cache. Approval gates persist their request, pause execution, and resume only after an authorized workspace member decides. Runtime events publish to `run:{tenant_id}:{run_id}:events`; each payload carries the workspace scope.

Crew definitions round trip through JSONC or YAML. Every task must name a registered Pydantic output type, and the builder passes it to CrewAI as `output_pydantic`. The sandbox bridge runs a coder and reviewer team, executes each attempt in an isolated Docker container, emits code and terminal output, and requires both a successful verification command and reviewer approval. `AutoGenCodeExecutionTool` exposes the same runner to Crew agents.

Persistent bots now store conversation threads in scoped database rows, schedule Markdown routines using cron or intervals, and invoke full workflows. `GatewayBotResponder` connects bot chat to the budgeted model gateway. Approval coordination checkpoints sensitive workflow/routine actions, records decisions in immutable audit rows, and resumes from the saved run state. One-time computer grants are consumed durably; routine-wide grants are bound to a specific action type and description.

The implementation is source only. Production images do not install the orchestration dependencies until their complete dependency trees meet the repository's exact license allowlist. The test environment uses replayed model responses, so live provider calls remain outside this phase's test evidence.

## Plugin kernel

`nexus_kernel` is a small container (scoped services, reversible registrations, five event modes, a dependency-driven plugin lifecycle, YAML rows with patch layers). `nexus_plugins` mounts the runtime's capabilities on it: database/Redis/Qdrant connections, model access, checkpoints, tools and the sandbox supervisor with its Docker provider and AutoGen runner. The API and workers boot `nexus_plugins/default.yaml` through `create_default_services()`. Print the list with `python -m nexus_plugins dump-config`. See the "Plugin architecture" section of `AGENTS.md` for the rules.
