import { contextBridge, ipcRenderer } from "electron";

interface FolderInfo { root: string; name: string; files: Array<{ path: string; size: number }>; truncated: boolean }

// The only surface the web app can reach: folder access and notifications. No Node, no file paths outside the mounted folder.
contextBridge.exposeInMainWorld("nexusDesktop", {
  platform: process.platform,
  version: ipcRenderer.sendSync("desktop:version") as string,
  openFolder: (): Promise<FolderInfo | null> => ipcRenderer.invoke("workspace:open"),
  getFolder: (): Promise<FolderInfo | null> => ipcRenderer.invoke("workspace:get"),
  getProjects: (): Promise<Array<{root:string;name:string}>> => ipcRenderer.invoke("workspace:projects"),
  selectProject: (root: string | null): Promise<FolderInfo | null> => ipcRenderer.invoke("workspace:select", root),
  createProject: (): Promise<FolderInfo | null> => ipcRenderer.invoke("workspace:create"),
  signInAccount: (provider: string, accessToken: string): Promise<void> => ipcRenderer.invoke("account:login", provider, accessToken),
  installAccountApp: (provider: string): Promise<void> => ipcRenderer.invoke("account:install", provider),
  getSettings: () => ipcRenderer.invoke("desktop:settings"),
  updateSettings: (patch: unknown) => ipcRenderer.invoke("desktop:update-settings", patch),
  chooseDownloadDirectory: () => ipcRenderer.invoke("desktop:download-directory"),
  openNotificationSettings: () => ipcRenderer.invoke("desktop:notification-settings"),
  readTextFiles: (maxBytes?: number): Promise<Array<{ path: string; content: string }>> => ipcRenderer.invoke("workspace:readTextFiles", maxBytes ?? 900_000),
  readFile: (path: string): Promise<string | null> => ipcRenderer.invoke("workspace:readFile", path),
  writeFile: (path: string, data: string | ArrayBuffer) => ipcRenderer.invoke("workspace:writeFile", path, typeof data === "string" ? data : new Uint8Array(data)),
  notify: (title: string, body: string): void => ipcRenderer.send("desktop:notify", String(title).slice(0, 120), String(body).slice(0, 240)),
  hideQuickBar: (): void => ipcRenderer.send("quickbar:hide"),
  onFolderChanged: (listener: (folder: FolderInfo | null) => void): (() => void) => {
    const handler = (_event: unknown, folder: FolderInfo | null): void => listener(folder);
    ipcRenderer.on("workspace:changed", handler);
    return () => { ipcRenderer.removeListener("workspace:changed", handler); };
  },
});
