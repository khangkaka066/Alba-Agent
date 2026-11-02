import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { readFileText, readTextFiles, resolveInside, scanFolder, writeFileSafe } from "./workspace-fs";

async function fixture(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "nexus-ws-"));
  await mkdir(join(root, "src", "auth"), { recursive: true });
  await mkdir(join(root, "node_modules", "dep"), { recursive: true });
  await mkdir(join(root, ".git"), { recursive: true });
  await writeFile(join(root, "src", "auth", "service.py"), "print('auth')\n");
  await writeFile(join(root, "README.md"), "# Project\n");
  await writeFile(join(root, ".env"), "SECRET=1\n");
  await writeFile(join(root, "deploy.pem"), "-----BEGIN-----\n");
  await writeFile(join(root, "logo.py"), Buffer.from([112, 0, 1, 2]));
  await writeFile(join(root, "node_modules", "dep", "index.js"), "x");
  return root;
}

test("scanning skips dependencies, VCS data and dot-folders", async () => {
  const root = await fixture();
  const { files, truncated } = await scanFolder(root);
  assert.equal(truncated, false);
  assert.deepEqual(files.map((f) => f.path).sort(), ["README.md", "deploy.pem", "logo.py", "src/auth/service.py"]);
});

test("the team only reads text files, never secrets or binaries", async () => {
  const root = await fixture();
  const { files } = await scanFolder(root);
  const read = await readTextFiles(root, files, 1_000_000);
  assert.deepEqual(read.map((f) => f.path).sort(), ["README.md", "src/auth/service.py"]);
  assert.equal((await readTextFiles(root, files, 5)).length, 0, "the byte budget is respected");
  assert.equal(await readFileText(root, ".env"), null);
  assert.match(String(await readFileText(root, "README.md")), /Project/);
});

test("paths cannot leave the mounted folder", async () => {
  const root = await fixture();
  for (const bad of ["../outside.txt", "src/../../outside.txt", "/etc/passwd", "a\0b"]) await assert.rejects(resolveInside(root, bad), Error, bad);
  const outside = await mkdtemp(join(tmpdir(), "nexus-out-"));
  await symlink(outside, join(root, "link"));
  await assert.rejects(resolveInside(root, "link/stolen.txt"), /escapes/);
  const blocked = await writeFileSafe(root, "link/stolen.txt", "x");
  assert.equal(blocked.ok, false);
  assert.match((await resolveInside(root, "new/dir/file.md")), /new\/dir\/file\.md$/);
});

test("accepted files are written inside the folder, creating directories, and protected places refuse", async () => {
  const root = await fixture();
  const ok = await writeFileSafe(root, "docs/report.md", "# Report\n");
  assert.deepEqual(ok, { ok: true, path: "docs/report.md" });
  assert.equal(await readFile(join(root, "docs", "report.md"), "utf8"), "# Report\n");
  const bytes = await writeFileSafe(root, "assets/chart.png", new Uint8Array([137, 80, 78, 71]));
  assert.equal(bytes.ok, true);
  for (const protectedPath of [".git/config", ".env", "deploy.pem"]) assert.equal((await writeFileSafe(root, protectedPath, "x")).ok, false, protectedPath);
  assert.equal((await writeFileSafe(root, "../escape.txt", "x")).ok, false);
});
