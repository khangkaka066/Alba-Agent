# Computer sandbox

`DockerSandboxSupervisor` runs Python for one `(tenant_id, workspace_id, run_id)` in a local Docker container. It uses a separate bind-mounted run directory, no container network, a read-only root filesystem, dropped capabilities, process and resource limits, and a timeout. Standard output and errors stream to the runtime event emitter. The supervisor returns exit status, elapsed time, and artifact paths relative to the run directory.

Workflow run inputs may stage small operator-supplied files into that run directory. File names are constrained to workspace-relative paths, symlinks are not followed while writing, and the total request payload is bounded by the API's 1 MiB limit.

`ComputerSandboxSupervisor` now provisions persistent shared workspace computers and private bot/run computers, with scoped database records and access checks. `DockerSandboxProvider` keeps a locked-down container alive across shell calls, file transfers, browser hook calls, and screen frames. `screen_proxy` streams changed PNG frames; a configured browser hook must supply the browser action and frame. Cloud provider classes accept injected drivers for E2B, Daytona, CreateOS, and Boat. Their SDK integrations are not bundled.

Compose builds this Python execution image as `nexus-sandbox-python:3.11`; the API and worker use the host Docker socket and shared host root to launch scoped child containers. The sandbox image itself has no network access or published port. A graphical desktop and browser driver are not included, so screen routes stream frames only when a driver has supplied PNG snapshots.

## Local mode (macOS, no Docker)

`LocalSandboxProvider` (`local_provider.py`) runs a computer's commands on the host inside a Seatbelt sandbox (`sandbox-exec`), with a command policy (`execution_policy.py`) in front of it. It is opt-in: the `sandbox-local` plugin row is disabled by default; enable it with a plugin patch (`disabled: false`) and set `NEXUS_SANDBOX_PROVIDER=local`. The API and worker must then run on the macOS host.

Two layers, in this order:

1. **Policy (text).** Deny > Ask > Allow. Denied: reading `.env` and credential folders, `sudo`, recursive delete of root or home, download piped to a shell, disk damage. Ask: network tools and package installs, and creating files that run by themselves later (shell rc files, git hooks, `.vscode`, cron, launchd). An Ask goes through the existing approval boundary (`external_action`); with no approval guard it is an error, and the provider refuses it again if it is reached without an approval. `strict` mode asks before every command. There is no allowlist of "safe" commands.
2. **Kernel sandbox.** Whatever the command says, it can write only inside its own computer directory, cannot read credential files or other computers' directories, has no network (an approved command that needs it gets the network for that one call), receives none of the host's environment variables, and cannot grow one file past 1 GiB. A timeout kills the whole process tree.

What it does **not** do: it works on macOS only (Apple marks `sandbox-exec` deprecated but still ships it); Seatbelt cannot filter by host, so the network is open or closed; it sets no memory or process-count limit; the rest of the host filesystem stays readable except the paths above; the text policy can be disguised (the kernel layer cannot), so treat the policy as a courtesy and the sandbox as the guarantee. Windows and Linux are not supported by this provider; use Docker there.

