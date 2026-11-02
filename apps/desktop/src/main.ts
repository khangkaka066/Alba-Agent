import { BrowserWindow, Menu, Notification, app, dialog, globalShortcut, ipcMain, screen, shell, type IpcMainEvent, type IpcMainInvokeEvent, type MenuItemConstructorOptions } from "electron";
import { basename, join } from "node:path";
import { existsSync, statSync } from "node:fs";
import { loadSettings, resolveWebUrl, saveSettings } from "./settings";
import { readFileText, readTextFiles, scanFolder, writeFileSafe, type FolderScan } from "./workspace-fs";

const QUICK_SHORTCUT = "CommandOrControl+Shift+Space";
const BACKGROUND = "#090A0F";
const isMac = process.platform === "darwin";

let settings = loadSettings(app.getPath("userData"));
const webUrl = resolveWebUrl(process.env.NEXUS_WEB_URL, settings.webUrl);
const origin = new URL(webUrl).origin;
let mainWindow: BrowserWindow | null = null;
let quickBar: BrowserWindow | null = null;
let folderRoot: string | null = null;
let lastScan: FolderScan = { files: [], truncated: false };

// Nothing leaves the machine except the traffic to your own NexusAgent server.
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
  settings = { ...settings, lastFolder: folderRoot ?? undefined };
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

function offlinePage(): string {
  const html = `<body style="margin:0;background:${BACKGROUND};color:#e6e6e6;font:15px system-ui;display:grid;place-content:center;height:100vh;text-align:center;-webkit-app-region:drag">
  <h2 style="margin:0 0 8px">Cannot reach NexusAgent</h2><p style="color:#9a9a9a;margin:0 0 18px">Is the server running at <b>${origin}</b>?<br>Start it with <code>docker compose up -d</code>, or set NEXUS_WEB_URL.</p>
  <a href="${webUrl}/studio" style="color:#8fb0ff;-webkit-app-region:no-drag">Try again</a></body>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function guardNavigation(window: BrowserWindow): void {
  const external = (url: string): void => { try { const { protocol } = new URL(url); if (protocol === "https:" || protocol === "http:") void shell.openExternal(url); } catch { /* ignore */ } };
  window.webContents.setWindowOpenHandler(({ url }) => { external(url); return { action: "deny" }; });
  window.webContents.on("will-navigate", (event, url) => { if (!url.startsWith("data:") && new URL(url).origin !== origin) { event.preventDefault(); external(url); } });
}

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440, height: 900, minWidth: 960, minHeight: 600, show: false, backgroundColor: BACKGROUND, title: "NexusAgent",
    titleBarStyle: isMac ? "hiddenInset" : "hidden",
    ...(isMac ? { trafficLightPosition: { x: 16, y: 14 } } : { titleBarOverlay: { color: "#191919", symbolColor: "#cfcfcf", height: 46 } }),
    webPreferences: { preload: join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  guardNavigation(mainWindow);
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.webContents.on("did-fail-load", (_event, _code, _description, url, isMainFrame) => { if (isMainFrame && !url.startsWith("data:")) void mainWindow?.loadURL(offlinePage()); });
  mainWindow.on("focus", () => { if (folderRoot) void folderInfo().then((info) => mainWindow?.webContents.send("workspace:changed", info)); });
  mainWindow.on("closed", () => { mainWindow = null; });
  void mainWindow.loadURL(`${webUrl}/studio`);
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
  ipcMain.on("desktop:version", (event) => { event.returnValue = trusted(event) ? app.getVersion() : ""; });
  ipcMain.handle("workspace:open", async (event) => { if (!trusted(event)) return null; await chooseFolder(); return folderInfo(); });
  ipcMain.handle("workspace:get", async (event) => (trusted(event) ? folderInfo() : null));
  ipcMain.handle("workspace:readTextFiles", async (event, maxBytes: number) => (trusted(event) && folderRoot ? readTextFiles(folderRoot, lastScan.files, Math.min(Math.max(Number(maxBytes) || 0, 0), 1_000_000)) : []));
  ipcMain.handle("workspace:readFile", async (event, path: string) => (trusted(event) && folderRoot && typeof path === "string" ? readFileText(folderRoot, path) : null));
  ipcMain.handle("workspace:writeFile", async (event, path: string, data: string | Uint8Array) => {
    if (!trusted(event) || !folderRoot || typeof path !== "string") return { ok: false, error: "No folder is open" };
    const result = await writeFileSafe(folderRoot, path, data);
    if (result.ok) void folderInfo().then((info) => mainWindow?.webContents.send("workspace:changed", info));
    return result;
  });
  ipcMain.on("desktop:notify", (event, title: string, body: string) => {
    if (!trusted(event) || !Notification.isSupported() || (mainWindow?.isFocused() && !quickBar?.isVisible())) return;
    const notice = new Notification({ title: String(title), body: String(body), silent: false });
    notice.on("click", () => { mainWindow?.show(); mainWindow?.focus(); });
    notice.show();
  });
  ipcMain.on("quickbar:hide", (event) => { if (trusted(event)) quickBar?.hide(); });
}

app.on("second-instance", () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } });
app.on("window-all-closed", () => { if (!isMac) app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createMainWindow(); });
app.on("will-quit", () => globalShortcut.unregisterAll());

void app.whenReady().then(async () => {
  registerIpc();
  buildMenu();
  const argument = process.argv.find((item) => item.startsWith("--workspace="))?.slice("--workspace=".length);
  await mountFolder(argument ?? process.env.NEXUS_DESKTOP_WORKSPACE ?? settings.lastFolder ?? null);
  createMainWindow();
  if (!globalShortcut.register(QUICK_SHORTCUT, toggleQuickBar)) console.warn(`Global shortcut ${QUICK_SHORTCUT} is taken by another app; use File → Quick Task.`);
});
