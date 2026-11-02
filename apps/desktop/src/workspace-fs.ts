import { lstat, mkdir, readFile, readdir, realpath, stat, writeFile } from "node:fs/promises";
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";

export interface FolderFile { path: string; size: number }
export interface FolderScan { files: FolderFile[]; truncated: boolean }
export type WriteResult = { ok: true; path: string } | { ok: false; error: string };

export const IGNORED_DIRECTORIES = new Set([".git", "node_modules", ".next", "dist", "build", "out", "release", ".venv", "venv", "__pycache__", ".idea", ".vscode", ".cache", "coverage", "target", ".turbo", ".pytest_cache", ".mypy_cache"]);
const TEXT_EXTENSIONS = new Set([".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".csv", ".html", ".css", ".scss", ".sql", ".sh", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".rb", ".php", ".xml", ".ini", ".cfg", ".rst", ".tsv"]);
// Files that usually hold credentials never leave the machine, even from a folder the user mounted.
const SECRET_NAME = /^(\.env(\..*)?|\.npmrc|\.pypirc|id_(rsa|ed25519|ecdsa|dsa)(\.pub)?|.*\.(pem|key|p12|pfx|keystore)|credentials(\..*)?|secrets?(\..*)?)$/i;
export const MAX_FILES = 5000;
export const MAX_DEPTH = 12;
export const MAX_TEXT_FILE_BYTES = 200_000;
export const MAX_WRITE_BYTES = 100_000_000;

export const isSecretName = (name: string): boolean => SECRET_NAME.test(name);

/** Resolves a folder-relative path and refuses anything that would land outside the root, including through symlinks. */
export async function resolveInside(root: string, rel: string): Promise<string> {
  if (!rel || rel.includes("\0") || isAbsolute(rel) || rel.split(/[\\/]/).some((part) => part === "..")) throw new Error("Path must be relative and stay inside the folder");
  const realRoot = await realpath(root);
  const target = resolve(realRoot, rel);
  if (target !== realRoot && !target.startsWith(realRoot + sep)) throw new Error("Path escapes the folder");
  // Walk up to the deepest existing ancestor and make sure it, once symlinks are resolved, is still inside the root.
  let probe = target;
  for (;;) {
    try { const real = await realpath(probe); if (real !== realRoot && !real.startsWith(realRoot + sep)) throw new Error("Path escapes the folder through a link"); break; }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      const parent = dirname(probe);
      if (parent === probe) break;
      probe = parent;
    }
  }
  return target;
}

export async function scanFolder(root: string): Promise<FolderScan> {
  const files: FolderFile[] = [];
  let truncated = false;
  const realRoot = await realpath(root); // paths are reported relative to the real folder, so a symlinked root (/tmp, /var) still works
  const walk = async (directory: string, depth: number): Promise<void> => {
    if (truncated || depth > MAX_DEPTH) return;
    let entries;
    try { entries = await readdir(directory, { withFileTypes: true }); } catch { return; }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (files.length >= MAX_FILES) { truncated = true; return; }
      if (entry.name.startsWith(".") && entry.name !== ".github") continue;
      const full = join(directory, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) { if (!IGNORED_DIRECTORIES.has(entry.name)) await walk(full, depth + 1); continue; }
      if (!entry.isFile()) continue;
      try { files.push({ path: relative(realRoot, full).split(sep).join("/"), size: (await stat(full)).size }); } catch { /* vanished while scanning */ }
    }
  };
  await walk(realRoot, 0);
  return { files, truncated };
}

const looksBinary = (buffer: Buffer): boolean => buffer.subarray(0, 4096).includes(0);

/** Text files the team may read, within a total byte budget. Secrets, binaries and oversized files are skipped. */
export async function readTextFiles(root: string, files: FolderFile[], maxBytes: number): Promise<Array<{ path: string; content: string }>> {
  const out: Array<{ path: string; content: string }> = [];
  let used = 0;
  for (const file of files) {
    const name = basename(file.path);
    if (isSecretName(name) || !TEXT_EXTENSIONS.has(extname(name).toLowerCase()) || file.size > MAX_TEXT_FILE_BYTES || file.size === 0) continue;
    if (used + file.size > maxBytes) continue;
    try {
      const buffer = await readFile(await resolveInside(root, file.path));
      if (looksBinary(buffer)) continue;
      out.push({ path: file.path, content: buffer.toString("utf8") });
      used += buffer.byteLength;
    } catch { /* unreadable files are left out */ }
  }
  return out;
}

export async function readFileText(root: string, rel: string): Promise<string | null> {
  try {
    if (isSecretName(basename(rel))) return null;
    const target = await resolveInside(root, rel);
    const info = await lstat(target);
    if (!info.isFile() || info.size > MAX_WRITE_BYTES) return null;
    return await readFile(target, "utf8");
  } catch { return null; }
}

export async function writeFileSafe(root: string, rel: string, data: string | Uint8Array): Promise<WriteResult> {
  try {
    const parts = rel.split(/[\\/]/);
    if (parts.includes(".git") || parts.some((part) => isSecretName(part) && part === parts[parts.length - 1])) return { ok: false, error: "That location is protected" };
    const size = typeof data === "string" ? Buffer.byteLength(data) : data.byteLength;
    if (size > MAX_WRITE_BYTES) return { ok: false, error: "File is too large" };
    const target = await resolveInside(root, rel);
    try { if ((await lstat(target)).isSymbolicLink()) return { ok: false, error: "Refusing to write through a symbolic link" }; } catch { /* new file */ }
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, data);
    return { ok: true, path: rel.split(sep).join("/") };
  } catch (error) { return { ok: false, error: error instanceof Error ? error.message : "Write failed" }; }
}
