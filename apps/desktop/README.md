# NexusAgent Desktop

A native window for NexusAgent, built with Electron. It connects to your local Docker stack (default
`http://localhost:3000`) or to any HTTPS server, and adds what a browser cannot do:

- **Open Local Folder…** (`⌘/Ctrl+O`): mount a project folder. Agents receive your text files (secrets, binaries and
  dependency folders are never sent). Files an agent produces appear in the workbench as a diff; **Accept** writes them
  back into the real folder, **Reject** leaves it untouched. Writes are confined to the mounted folder.
- **Quick Task** (`⌘/Ctrl+Shift+Space`, global): a floating bar to delegate a task to your agent team from any app.
- **Native notifications** when a run needs your approval or finishes while the window is in the background.
- Frameless dark window (`hiddenInset` title bar on macOS, overlay controls on Windows and Linux).

## Run

```bash
docker compose up -d                       # the NexusAgent stack
pnpm --filter @nexus/desktop dev           # compile and start the app
```

| Setting | How |
|---|---|
| Server URL | `NEXUS_WEB_URL=https://studio.example.com` (HTTPS, or HTTP only for localhost), or `webUrl` in `settings.json` in the app data folder |
| Open a folder at launch | `--workspace=/path/to/project` or `NEXUS_DESKTOP_WORKSPACE` |

## Build installers

```bash
pnpm --filter @nexus/desktop build         # installer for the OS you are on
pnpm --filter @nexus/desktop build:mac     # .dmg
pnpm --filter @nexus/desktop build:win     # .exe (NSIS installer), build on Windows
pnpm --filter @nexus/desktop build:linux   # .AppImage, build on Linux
```

Installers land in `apps/desktop/release/`. On macOS the DMG step needs a `python` command on `PATH` (for example `ln -s $(which python3) /usr/local/bin/python`). They are unsigned: macOS asks you to confirm the first launch, Windows shows
SmartScreen. Sign and notarize them with your own certificates before distributing.

## Security model

The web app runs with `contextIsolation`, no Node integration and the renderer sandbox. The only bridge is
`window.nexusDesktop` (folder access and notifications), honoured only for pages served from the configured server origin.
Navigation to other origins opens in your browser. The app sends nothing anywhere except to your NexusAgent server.
