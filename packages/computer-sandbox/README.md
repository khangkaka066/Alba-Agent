# Computer sandbox

`DockerSandboxSupervisor` runs Python for one `(tenant_id, workspace_id, run_id)` in a local Docker container. It uses a separate bind-mounted run directory, no container network, a read-only root filesystem, dropped capabilities, process and resource limits, and a timeout. Standard output and errors stream to the runtime event emitter. The supervisor returns exit status, elapsed time, and artifact paths relative to the run directory.

Workflow run inputs may stage small operator-supplied files into that run directory. File names are constrained to workspace-relative paths, symlinks are not followed while writing, and the total request payload is bounded by the API's 1 MiB limit.

`ComputerSandboxSupervisor` now provisions persistent shared workspace computers and private bot/run computers, with scoped database records and access checks. `DockerSandboxProvider` keeps a locked-down container alive across shell calls, file transfers, browser hook calls, and screen frames. `screen_proxy` streams changed PNG frames; a configured browser hook must supply the browser action and frame. Cloud provider classes accept injected drivers for E2B, Daytona, CreateOS, and Boat. Their SDK integrations are not bundled.

Compose builds this Python execution image as `nexus-sandbox-python:3.11`; the API and worker use the host Docker socket and shared host root to launch scoped child containers. The sandbox image itself has no network access or published port. A graphical desktop and browser driver are not included, so screen routes stream frames only when a driver has supplied PNG snapshots.
