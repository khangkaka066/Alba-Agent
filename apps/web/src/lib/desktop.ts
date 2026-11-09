/** The bridge the Electron shell exposes as `window.nexusDesktop`. It is absent in a normal browser. */
export type FolderInfo = { root: string; name: string; files: Array<{ path: string; size: number }>; truncated: boolean };
export type WriteResult = { ok: true; path: string } | { ok: false; error: string };
export type ProjectInfo = {root:string;name:string};
export type DesktopApplicationSettings = {preventSleep:boolean;keepInMenuBar:boolean;notificationsEnabled:boolean;soundEnabled:boolean;volume:number;downloadDirectory:string;version:string;powerSaveBlockerActive:boolean;remoteControlAvailable:boolean};

export interface NexusDesktop {
  platform: string;
  version: string;
  openFolder(): Promise<FolderInfo | null>;
  getFolder(): Promise<FolderInfo | null>;
  getProjects(): Promise<ProjectInfo[]>;
  selectProject(root:string|null): Promise<FolderInfo|null>;
  createProject(): Promise<FolderInfo|null>;
  signInAccount(provider: string, accessToken: string): Promise<void>;
  installAccountApp(provider: string): Promise<void>;
  getSettings(): Promise<DesktopApplicationSettings>;
  updateSettings(patch:Partial<Pick<DesktopApplicationSettings,'preventSleep'|'keepInMenuBar'|'notificationsEnabled'|'soundEnabled'|'volume'>>): Promise<DesktopApplicationSettings>;
  chooseDownloadDirectory(): Promise<DesktopApplicationSettings|null>;
  openNotificationSettings(): Promise<void>;
  readTextFiles(maxBytes?: number): Promise<Array<{ path: string; content: string }>>;
  readFile(path: string): Promise<string | null>;
  writeFile(path: string, data: string | ArrayBuffer): Promise<WriteResult>;
  notify(title: string, body: string): void;
  hideQuickBar(): void;
  onFolderChanged(listener: (folder: FolderInfo | null) => void): () => void;
}

declare global {
  interface Window { nexusDesktop?: NexusDesktop }
}

export function getDesktop(): NexusDesktop | null {
  return typeof window !== "undefined" && window.nexusDesktop ? window.nexusDesktop : null;
}
