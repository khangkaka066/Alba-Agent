import { lstat, readFile, readdir, realpath } from "node:fs/promises";
import { dirname, join } from "node:path";

const allowed = new Set([
  "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "ISC",
  "Zlib", "Unlicense", "CC0-1.0", "CC-BY-3.0", "CC-BY-4.0",
  "BlueOak-1.0.0", "Python-2.0", "Artistic-2.0", "MPL-2.0",
]);
const denied = /^(?:AGPL|GPL|SSPL|BUSL)(?:-|$)/i;
const restricted = /(?:dify|langgenius|business source license|source available license)/i;
const packages = new Map();
const scannedDirectories = new Set();
const failures = [];

async function scanModuleDirectory(directory) {
  let actual;
  try { actual = await realpath(directory); } catch { return; }
  if (scannedDirectories.has(actual)) return;
  scannedDirectories.add(actual);
  let entries;
  try { entries = await readdir(directory, { withFileTypes: true }); } catch { return; }
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory() && entry.name.startsWith("@")) {
      let scoped;
      try { scoped = await readdir(path, { withFileTypes: true }); } catch { continue; }
      for (const item of scoped) await visitLink(join(path, item.name));
    } else {
      await visitLink(path);
    }
  }
}

async function visitLink(path) {
  try {
    if (!(await lstat(path)).isSymbolicLink()) return;
    const target = await realpath(path);
    const metadata = JSON.parse(await readFile(join(target, "package.json"), "utf8"));
    if (typeof metadata.name !== "string" || typeof metadata.version !== "string" || metadata.private) return;
    packages.set(`${metadata.name}@${metadata.version}`, metadata.license);
    await scanModuleDirectory(dirname(target));
  } catch { /* Broken links and non-package links are not resolved dependencies. */ }
}

await scanModuleDirectory("apps/web/node_modules");
await scanModuleDirectory("node_modules");
if (packages.size === 0) {
  console.error("No installed package metadata found; run pnpm install --frozen-lockfile first.");
  process.exit(2);
}
if (process.argv.includes("--inventory")) {
  for (const [name, license] of [...packages.entries()].sort(([left], [right]) => left.localeCompare(right))) console.log(`${name}\t${String(license ?? "missing")}`);
  process.exit(0);
}
for (const [name, declared] of packages) {
  const identifiers = typeof declared === "string" ? declared.match(/[A-Za-z0-9.+-]+/g) ?? [] : [];
  const licenses = identifiers.filter((license) => license !== "AND" && license !== "OR" && license !== "WITH");
  if (licenses.some((license) => denied.test(license)) || restricted.test(`${name} ${String(declared ?? "")}`)) {
    failures.push(`${name}: ${String(declared ?? "missing license metadata")}`);
  }
}
if (process.argv.includes("--expanded-diff")) {
  for (const [name, license] of [...packages.entries()].sort(([left], [right]) => left.localeCompare(right))) {
    console.log(`${name}\t${String(license ?? "missing")}`);
  }
  process.exit(0);
}
if (failures.length) {
  console.error(`License check failed for ${failures.length} of ${packages.size} reachable npm packages:`);
  for (const failure of failures.sort()) console.error(`- ${failure}`);
  process.exit(1);
}
console.log(`License check passed for ${packages.size} reachable npm packages.`);
