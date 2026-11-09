import { BrowserWindow, Menu, Notification, Tray, nativeImage, powerSaveBlocker, app, dialog, globalShortcut, ipcMain, screen, shell, type IpcMainEvent, type IpcMainInvokeEvent, type MenuItemConstructorOptions } from "electron";
import { accountProvider, scopeId, loginScript, ACCOUNT_INSTALL_URLS } from "./account-login";
import { basename, join } from "node:path";
import { createWriteStream, existsSync, mkdirSync, writeFileSync, chmodSync, readFileSync, statSync, truncateSync, type WriteStream } from "node:fs";
import { loadSettings, resolveWebUrl, saveSettings, rememberFolder, preferencePatch } from "./settings";
import { Stack } from "./stack";
import { startupPage } from "./startup-page";
import { readFileText, readTextFiles, scanFolder, writeFileSafe, type FolderScan } from "./workspace-fs";

const QUICK_SHORTCUT = "CommandOrControl+Shift+Space";
const BACKGROUND = "#090A0F";
const isMac = process.platform === "darwin";

// Reuse an earlier installation in place; rebranding must not create an empty account store.
const defaultUserData = app.getPath("userData");
const predecessors = [join(app.getPath("appData"), "NexusAgent"), join(app.getPath("appData"), "Nexus Agent")];
const userDataDirectory = existsSync(join(defaultUserData, "settings.json")) ? defaultUserData : predecessors.find((directory) => existsSync(join(directory, "settings.json"))) ?? defaultUserData;
app.setName("Alba Agent");
app.setPath("userData", userDataDirectory);
let settings = loadSettings(userDataDirectory);
// Embedded mode: the installer ships the whole stack (Postgres, Redis, Qdrant, API, worker, web) and this process starts it, so nothing else
// has to be installed. An explicit NEXUS_WEB_URL (or a saved server) still means "connect to that server instead".
const runtimeDirectory = process.env.NEXUS_RUNTIME_DIR ?? (app.isPackaged ? join(process.resourcesPath, "runtime") : join(__dirname, "..", "runtime", `${process.platform === "darwin" ? "mac" : "win"}-${process.arch}`));
const embedded = !process.env.NEXUS_WEB_URL && !settings.webUrl && existsSync(join(runtimeDirectory, "manifest.json"));
let stack: Stack | null = null;
let webUrl = resolveWebUrl(process.env.NEXUS_WEB_URL, settings.webUrl);
let origin = new URL(webUrl).origin;
let mainWindow: BrowserWindow | null = null;
let quickBar: BrowserWindow | null = null;
let folderRoot: string | null = null;
let lastScan: FolderScan = { files: [], truncated: false };
let tray: Tray | null = null;
let powerBlocker: number | null = null;
let downloadHandlerInstalled = false;

function showMainWindow(): void {
  if (!mainWindow) { const window = createMainWindow(); void window.loadURL(`${webUrl}/studio`); }
  if (mainWindow?.isMinimized()) mainWindow.restore();
  mainWindow?.show(); mainWindow?.focus();
}

function applyApplicationSettings(): void {
  if (settings.preventSleep && powerBlocker === null) powerBlocker = powerSaveBlocker.start("prevent-display-sleep");
  if (!settings.preventSleep && powerBlocker !== null) { powerSaveBlocker.stop(powerBlocker); powerBlocker = null; }
  if (settings.keepInMenuBar !== false && !tray) {
    const icon = nativeImage.createFromPath(join(__dirname, "..", "build", "icon.png")).resize({ width: 18, height: 18 });
    tray = new Tray(icon); tray.setToolTip("Alba Agent");
    tray.setContextMenu(Menu.buildFromTemplate([{ label: "Open Alba Agent", click: showMainWindow }, { type: "separator" }, { label: "Quit Alba Agent", click: () => app.quit() }]));
    tray.on("click", showMainWindow);
  }
  if (settings.keepInMenuBar === false && tray) { tray.destroy(); tray = null; }
}

function applicationSettings() {
  return { preventSleep: settings.preventSleep ?? false, keepInMenuBar: settings.keepInMenuBar ?? true, notificationsEnabled: settings.notificationsEnabled ?? true,
    soundEnabled: settings.soundEnabled ?? false, volume: settings.volume ?? 1, downloadDirectory: settings.downloadDirectory ?? app.getPath("downloads"),
    version: app.getVersion(), powerSaveBlockerActive: powerBlocker !== null && powerSaveBlocker.isStarted(powerBlocker), remoteControlAvailable: false };
}

// Nothing leaves the machine except the traffic to your own Alba Agent server.
app.commandLine.appendSwitch("disable-features", "OutOfBlinkCors");
process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = "1";

if (!app.requestSingleInstanceLock()) app.quit();

const trusted = (event: IpcMainEvent | IpcMainInvokeEvent): boolean => {
  try { return new URL(event.senderFrame?.url ?? "").origin === origin; } catch { return false; }
};

async function folderInfo(): Promise<{ root: string; name: string; files: FolderScan["files"]; truncated: boolean } | null> {
  if (!folderRoot) return null;
  lastScan = await scanFolder(folderRoot);
  return { root: folderRoot, name: basename(folderRoot), ...lastScan };
}

async function mountFolder(directory: string | null): Promise<void> {
  folderRoot = directory && existsSync(directory) && statSync(directory).isDirectory() ? directory : null;
  settings = rememberFolder(settings, folderRoot);
  saveSettings(app.getPath("userData"), settings);
  const info = await folderInfo();
  for (const window of BrowserWindow.getAllWindows()) window.webContents.send("workspace:changed", info);
}

async function chooseFolder(): Promise<void> {
  const options = { title: "Open local folder", properties: ["openDirectory", "createDirectory"] as Array<"openDirectory" | "createDirectory"> };
  const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
  const chosen = result.filePaths[0];
  if (!result.canceled && chosen) await mountFolder(chosen);
}

const escapeHtml = (text: string): string => text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c);

function messagePage(title: string, detail: string): string {
  const html = `<body style="margin:0;background:${BACKGROUND};color:#e6e6e6;font:15px system-ui;display:grid;place-content:center;height:100vh;text-align:center;-webkit-app-region:drag">
  <h2 style="margin:0 0 8px">${escapeHtml(title)}</h2><p style="color:#9a9a9a;margin:0;max-width:640px;white-space:pre-wrap;font:12px ui-monospace,Menlo,monospace">${escapeHtml(detail)}</p></body>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

// One log file per service, so "it does not start" has something to read. Truncated when large; secrets are never written to these.
const logStreams = new Map<string, WriteStream>();
function serviceLog(service: string, line: string): void {
  let stream = logStreams.get(service);
  if (!stream) {
    const directory = join(app.getPath("userData"), "logs");
    mkdirSync(directory, { recursive: true });
    const file = join(directory, `${service}.log`);
    try { if (statSync(file).size > 5_000_000) truncateSync(file, 0); } catch { /* new file */ }
    stream = createWriteStream(file, { flags: "a" });
    logStreams.set(service, stream);
  }
  stream.write(`${new Date().toISOString()} ${line}\n`);
}

async function startEmbeddedStack(): Promise<boolean> {
  const mark = readFileSync(join(__dirname, "..", "build", "mark.svg"), "utf8");
  await mainWindow?.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(startupPage(mark, app.getLocale().startsWith("vi")))}`);
  stack = new Stack({
    runtime: runtimeDirectory, data: process.env.NEXUS_DESKTOP_DATA_DIR ?? join(app.getPath("userData"), "data"), executable: process.execPath,
    onStatus: (message) => serviceLog("startup", message), onLog: serviceLog,
  });
  try {
    await stack.start();
    webUrl = stack.webUrl;
    origin = new URL(webUrl).origin;
    return true;
  } catch (error) {
    await stack.stop();
    void mainWindow?.loadURL(messagePage("Alba Agent could not start", `${error instanceof Error ? error.message : String(error)}\n\nLogs: ${join(app.getPath("userData"), "logs")}`));
    return false;
  }
}

function offlinePage(): string {
  const html = `<body style="margin:0;background:${BACKGROUND};color:#e6e6e6;font:15px system-ui;display:grid;place-content:center;height:100vh;text-align:center;-webkit-app-region:drag">
  <h2 style="margin:0 0 8px">Cannot reach Alba Agent</h2><p style="color:#9a9a9a;margin:0 0 18px">${embedded ? `Alba Agent's background services stopped answering.<br>Quit and open the app again. Logs: ${escapeHtml(join(app.getPath("userData"), "logs"))}` : `Is the server running at <b>${origin}</b>?<br>Start it with <code>docker compose up -d</code>, or set NEXUS_WEB_URL.`}</p>
  <a href="${webUrl}/studio" style="color:#8fb0ff;-webkit-app-region:no-drag">Try again</a></body>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function guardNavigation(window: BrowserWindow): void {
  const external = (url: string): void => { try { const { protocol } = new URL(url); if (protocol === "https:" || protocol === "http:") void shell.openExternal(url); } catch { /* ignore */ } };
  window.webContents.setWindowOpenHandler(({ url }) => { external(url); return { action: "deny" }; });
  window.webContents.on("will-navigate", (event, url) => { if (!url.startsWith("data:") && new URL(url).origin !== origin) { event.preventDefault(); external(url); } });
}

function createMainWindow(): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 1440, height: 900, minWidth: 960, minHeight: 600, show: false, backgroundColor: BACKGROUND, title: "Alba Agent",
    titleBarStyle: isMac ? "hiddenInset" : "hidden",
    ...(isMac ? { trafficLightPosition: { x: 16, y: 14 } } : { titleBarOverlay: { color: "#191919", symbolColor: "#cfcfcf", height: 46 } }),
    webPreferences: { preload: join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  guardNavigation(mainWindow);
  if (!downloadHandlerInstalled) {
  downloadHandlerInstalled = true;
  mainWindow.webContents.session.on("will-download", (_event, item) => {
    if (settings.downloadDirectory && existsSync(settings.downloadDirectory)) item.setSavePath(join(settings.downloadDirectory, basename(item.getFilename())));
  });
  }
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.webContents.on("did-fail-load", (_event, _code, _description, url, isMainFrame) => { if (isMainFrame && !url.startsWith("data:")) void mainWindow?.loadURL(offlinePage()); });
  mainWindow.on("focus", () => { if (folderRoot) void folderInfo().then((info) => mainWindow?.webContents.send("workspace:changed", info)); });
  mainWindow.on("closed", () => { mainWindow = null; });
  return mainWindow;
}

function toggleQuickBar(): void {
  if (quickBar?.isVisible()) { quickBar.hide(); return; }
  if (!quickBar) {
    quickBar = new BrowserWindow({
      width: 680, height: 96, show: false, frame: false, resizable: false, movable: true, alwaysOnTop: true, skipTaskbar: true, transparent: true, hasShadow: true, backgroundColor: "#00000000",
      webPreferences: { preload: join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true },
    });
    guardNavigation(quickBar);
    quickBar.on("blur", () => quickBar?.hide());
    quickBar.on("closed", () => { quickBar = null; });
    void quickBar.loadURL(`${webUrl}/quickbar`);
  }
  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const { x, y, width } = display.workArea;
  quickBar.setPosition(Math.round(x + (width - 680) / 2), Math.round(y + 140));
  quickBar.show();
  quickBar.focus();
}

function buildMenu(): void {
  const template: MenuItemConstructorOptions[] = [
    ...(isMac ? [{ role: "appMenu" } as MenuItemConstructorOptions] : []),
    { label: "File", submenu: [
      { label: "Open Local Folder…", accelerator: "CommandOrControl+O", click: () => void chooseFolder() },
      { label: "Close Folder", enabled: true, click: () => void mountFolder(null) },
      { label: "Quick Task…", accelerator: QUICK_SHORTCUT, click: toggleQuickBar },
      { type: "separator" }, isMac ? { role: "close" } : { role: "quit" },
    ] },
    { role: "editMenu" }, { role: "viewMenu" }, { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function registerIpc(): void {
  ipcMain.handle("account:install", async (event, provider: unknown) => {
    if (!trusted(event)) throw new Error("Untrusted account request");
    await shell.openExternal(ACCOUNT_INSTALL_URLS[accountProvider(provider)]);
  });
  ipcMain.handle("account:login", async (event, selected: unknown, accessToken: unknown) => {
    if (!trusted(event) || !embedded || !stack || !isMac) throw new Error("Account sign-in requires the local macOS desktop application");
    const provider = accountProvider(selected);
    if (typeof accessToken !== "string" || accessToken.length > 8192) throw new Error("Sign in to Alba Agent first");
    const response = await fetch(`${stack.apiUrl}/api/v1/settings/subscriptions/accounts/${provider}/prepare`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` }, signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error("Could not prepare sign-in. Install the official provider application and retry");
    const scope = await response.json() as { tenant_id: unknown; workspace_id: unknown; provider: unknown };
    if (scope.provider !== provider) throw new Error("Invalid account provider response");
    const dataRoot = process.env.NEXUS_DESKTOP_DATA_DIR ?? join(app.getPath("userData"), "data");
    const profile = join(dataRoot, "account-clis", scopeId(scope.tenant_id), scopeId(scope.workspace_id), provider);
    const python = join(runtimeDirectory, "python", "bin", "python3");
    const helper = join(runtimeDirectory, "backend", "apps", "api", "app", "account_cli.py");
    if (!existsSync(python) || !existsSync(helper)) throw new Error("Update Alba Agent to use account sign-in");
    const launcher = join(profile, "sign-in.command");
    writeFileSync(launcher, loginScript([python, helper, "login", provider, profile, "--tools-dir", join(runtimeDirectory, "account-tools")]), { mode: 0o700 });
    chmodSync(launcher, 0o700);
    const error = await shell.openPath(launcher);
    if (error) throw new Error("Could not open the official sign-in window");
  });

  ipcMain.on("desktop:version", (event) => { event.returnValue = trusted(event) ? app.getVersion() : ""; });
  ipcMain.handle("workspace:open", async (event) => { if (!trusted(event)) return null; await chooseFolder(); return folderInfo(); });
  ipcMain.handle("workspace:get", async (event) => (trusted(event) ? folderInfo() : null));
  ipcMain.handle("workspace:projects", (event) => {
    if (!trusted(event)) return [];
    return (settings.recentFolders ?? []).filter((root) => existsSync(root) && statSync(root).isDirectory()).map((root) => ({ root, name: basename(root) }));
  });
  ipcMain.handle("workspace:select", async (event, root: string | null) => {
    if (!trusted(event) || (root !== null && (typeof root !== "string" || !(settings.recentFolders ?? []).includes(root)))) throw new Error("Select a previously opened project");
    await mountFolder(root); return folderInfo();
  });
  ipcMain.handle("workspace:create", async (event) => {
    if (!trusted(event)) return null;
    const options = { title: "New Alba Agent project", buttonLabel: "Create Project", properties: ["createDirectory", "showOverwriteConfirmation"] as Array<"createDirectory" | "showOverwriteConfirmation"> };
    const result = mainWindow ? await dialog.showSaveDialog(mainWindow, options) : await dialog.showSaveDialog(options);
    if (result.canceled || !result.filePath) return null;
    if (existsSync(result.filePath)) throw new Error("That folder already exists. Open it as a project instead.");
    mkdirSync(result.filePath, { mode: 0o700 }); await mountFolder(result.filePath); return folderInfo();
  });
  ipcMain.handle("desktop:settings", (event) => trusted(event) ? applicationSettings() : null);
  ipcMain.handle("desktop:update-settings", (event, patch: unknown) => {
    if (!trusted(event)) throw new Error("Untrusted settings request");
    settings = { ...settings, ...preferencePatch(patch) }; saveSettings(app.getPath("userData"), settings); applyApplicationSettings(); return applicationSettings();
  });
  ipcMain.handle("desktop:download-directory", async (event) => {
    if (!trusted(event)) return null;
    const options = { title: "Download location", defaultPath: settings.downloadDirectory ?? app.getPath("downloads"), properties: ["openDirectory", "createDirectory"] as Array<"openDirectory" | "createDirectory"> };
    const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
    if (!result.canceled && result.filePaths[0]) { settings.downloadDirectory = result.filePaths[0]; saveSettings(app.getPath("userData"), settings); }
    return applicationSettings();
  });
  ipcMain.handle("desktop:notification-settings", async (event) => {
    if (!trusted(event)) return;
    if (isMac) await shell.openExternal("x-apple.systempreferences:com.apple.preference.notifications");
    else if (process.platform === "win32") await shell.openExternal("ms-settings:notifications");
    else throw new Error("Open notification preferences in your system settings");
  });
  ipcMain.handle("workspace:readTextFiles", async (event, maxBytes: number) => (trusted(event) && folderRoot ? readTextFiles(folderRoot, lastScan.files, Math.min(Math.max(Number(maxBytes) || 0, 0), 1_000_000)) : []));
  ipcMain.handle("workspace:readFile", async (event, path: string) => (trusted(event) && folderRoot && typeof path === "string" ? readFileText(folderRoot, path) : null));
  ipcMain.handle("workspace:writeFile", async (event, path: string, data: string | Uint8Array) => {
    if (!trusted(event) || !folderRoot || typeof path !== "string") return { ok: false, error: "No folder is open" };
    const result = await writeFileSafe(folderRoot, path, data);
    if (result.ok) void folderInfo().then((info) => mainWindow?.webContents.send("workspace:changed", info));
    return result;
  });
  ipcMain.on("desktop:notify", (event, title: string, body: string) => {
    if (!trusted(event) || settings.notificationsEnabled === false || !Notification.isSupported() || (mainWindow?.isFocused() && !quickBar?.isVisible())) return;
    const notice = new Notification({ title: String(title), body: String(body), silent: true });
    notice.on("click", () => { mainWindow?.show(); mainWindow?.focus(); });
    notice.show();
  });
  ipcMain.on("quickbar:hide", (event) => { if (trusted(event)) quickBar?.hide(); });
}

app.on("second-instance", () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } });
app.on("window-all-closed", () => { if (settings.keepInMenuBar === false) app.quit(); });
app.on("activate", showMainWindow);
app.on("will-quit", () => globalShortcut.unregisterAll());

let quitting = false;
app.on("before-quit", (event) => {
  if (!stack || quitting) return;
  // Stop the services in order (database last) before the process goes away; a killed database would need crash recovery on every launch.
  event.preventDefault();
  quitting = true;
  void stack.stop().finally(() => app.exit(0));
});

void app.whenReady().then(async () => {
  registerIpc();
  buildMenu();
  const argument = process.argv.find((item) => item.startsWith("--workspace="))?.slice("--workspace=".length);
  await mountFolder(argument ?? process.env.NEXUS_DESKTOP_WORKSPACE ?? settings.lastFolder ?? null);
  createMainWindow();
  applyApplicationSettings();
  if (embedded) {
    if (await startEmbeddedStack()) void mainWindow?.loadURL(`${webUrl}/studio`);
  } else {
    void mainWindow?.loadURL(`${webUrl}/studio`);
  }
  if (!globalShortcut.register(QUICK_SHORTCUT, toggleQuickBar)) console.warn(`Global shortcut ${QUICK_SHORTCUT} is taken by another app; use File → Quick Task.`);
});
