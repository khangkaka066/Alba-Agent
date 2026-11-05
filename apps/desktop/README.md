# NexusAgent Desktop

The installer carries the whole product: Postgres, Redis, Qdrant, the API, the worker and the web app start
inside the app when you open it. **No Docker, no Python, nothing else to install.** macOS 15 or later on Apple Silicon (`arm64`) `.dmg`; there is no Intel or Windows installer.
It also adds what a browser cannot do:

- **Open Local Folder…** (`⌘/Ctrl+O`): mount a project folder. Agents receive your text files (secrets, binaries and
  dependency folders are never sent). Files an agent produces appear in the workbench as a diff; **Accept** writes them
  back into the real folder, **Reject** leaves it untouched. Writes are confined to the mounted folder.
- **Quick Task** (`⌘/Ctrl+Shift+Space`, global): a floating bar to delegate a task to your agent team from any app.
- **Native notifications** when a run needs your approval or finishes while the window is in the background.
- Frameless dark window (`hiddenInset` title bar on macOS, overlay controls on Windows and Linux).

## Run

Open the app. The first start creates your private database and secrets in the app-data folder
(`~/Library/Application Support/NexusAgent/data`, secrets file mode 0600), which takes about a minute; later starts take
under half a minute. Then connect a model provider in **Settings → Providers**. Agent commands run on your machine inside a
macOS sandbox (writes only in the run's own folder, no `.env` or credential reads, no network unless you approve a command;
see `packages/computer-sandbox/README.md`, "Local mode").

Files for support are in `~/Library/Application Support/NexusAgent/logs/` (one per service; no secrets).
To give the services model keys without the UI, put `NEXUS_*_API_KEY=` / `..._API_BASE=` lines in `data/nexus.env`.

Connect to a server instead of running locally (the embedded stack is then not started):

| Setting | How |
|---|---|
| Server URL | `NEXUS_WEB_URL=https://studio.example.com` (HTTPS, or HTTP only for localhost), or `webUrl` in `settings.json` in the app data folder |
| Open a folder at launch | `--workspace=/path/to/project` or `NEXUS_DESKTOP_WORKSPACE` |
| Developing the app | `pnpm --filter @nexus/desktop dev` after building the runtime (below); `NEXUS_RUNTIME_DIR` points at another runtime folder |

## Build installers

```bash
python3 scripts/package/build_runtime.py mac-arm64     # downloads, verifies (sha256) and assembles apps/desktop/runtime/mac-arm64
python3 scripts/package/verify_runtime.py mac-arm64    # portability audit + smoke run from a relocated copy; must pass
pnpm --filter @nexus/desktop build:mac                 # .dmg in apps/desktop/release/
# Not shipped: an Intel build (mac-x64) was built and passed verify_runtime under Rosetta, but only Apple Silicon is released.
```

`build_runtime.py` assembles a relocatable Python with the API requirements, Postgres 16, Redis 7.2.4 (built from source, BSD),
Qdrant 1.12.6, the API and packages, and the Next.js standalone web server. For the commands that agents run it adds Node 22 and
npm, git (built from source, relocatable), ffmpeg and ffprobe (built from source, LGPL, H.264 and AAC through macOS) and a
`headless-browser` command that uses an installed Chrome, Chromium, Edge or Brave. Pins are in `scripts/package/runtime.json`.
Needs Xcode command line tools (to build Redis, git and ffmpeg), Python 3.12 or newer for the script, and about 12 GB of free
disk space. The bundle is about 1.5 GB; the `.dmg` is smaller.

**What "runs on any machine" means here, and how it is checked.** Nothing in the bundle may depend on the machine that built it.
`verify_runtime.py` fails the build when a file has no code for the target CPU, loads a library that macOS does not ship (Homebrew,
`/usr/local`), starts with an interpreter path of the builder, or needs a newer macOS than `build.mac.minimumSystemVersion`
(`15.0`) promises. It then copies the runtime to a folder with a space in its name and runs Python, pytest, node, npm, git and
ffmpeg there with a PATH of system folders only. pip is told to answer as macOS 15, so the wheels it picks do not depend on the
builder's macOS (numpy, onnxruntime and orjson ship wheels that need 14 to 15). Lowering the floor means older pins of those
packages in `apps/api/requirements.txt`, which the Docker stack shares.

Agent commands see `python`, `node`, `npm`, `git`, `ffmpeg` and `ffprobe` from the bundle first (`NEXUS_SANDBOX_TOOLS_PATH`, set by
the app) and the system folders after; nothing from Homebrew is visible, so a task behaves the same on every Mac.

The installers are unsigned: macOS asks you to confirm the first launch (right-click, Open). Sign and notarize them with your
own certificates before distributing. The Windows build (`build:win`) needs its own runtime and a Windows sandbox and is not
available yet; see `tasks/todo.md`, Phase 36.

## Security model

The web app runs with `contextIsolation`, no Node integration and the renderer sandbox. The only bridge is
`window.nexusDesktop` (folder access and notifications), honoured only for pages served from the configured server origin.
Navigation to other origins opens in your browser. The app sends nothing anywhere except to your NexusAgent server.
