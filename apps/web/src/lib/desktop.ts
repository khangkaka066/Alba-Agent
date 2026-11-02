/** The bridge the Electron shell exposes as `window.nexusDesktop`. It is absent in a normal browser. */
export type FolderInfo = { root: string; name: string; files: Array<{ path: string; size: number }>; truncated: boolean };
export type WriteResult = { ok: true; path: string } | { ok: false; error: string };

export interface NexusDesktop {
  platform: string;
  version: string;
  openFolder(): Promise<FolderInfo | null>;
  getFolder(): Promise<FolderInfo | null>;
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
