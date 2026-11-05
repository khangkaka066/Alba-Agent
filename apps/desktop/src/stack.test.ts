import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { allowedUserEnv, freePort, generateSecrets, loadOrCreateSecrets, parseUserEnv, portInUse } from "./stack";

test("secrets are created once, kept private, and never regenerated over existing data", () => {
  const data = join(mkdtempSync(join(tmpdir(), "nexus-stack-")), "data");
  const first = loadOrCreateSecrets(data);
  assert.equal(loadOrCreateSecrets(data).postgresPassword, first.postgresPassword);
  assert.equal(statSync(join(data, "secrets.json")).mode & 0o077, 0, "group and others must have no access");
  assert.equal(Buffer.from(first.encryptionKeyBase64, "base64").length, 32);
  for (const value of [first.postgresPassword, first.runtimePassword, first.redisPassword]) assert.match(value, /^[A-Za-z0-9_-]+$/, "must be safe inside a connection URL");
});

test("an incomplete secrets file is refused, not silently replaced", () => {
  const data = mkdtempSync(join(tmpdir(), "nexus-stack-"));
  writeFileSync(join(data, "secrets.json"), JSON.stringify({ ...generateSecrets(), redisPassword: "" }));
  assert.throws(() => loadOrCreateSecrets(data), /incomplete/);
  assert.match(readFileSync(join(data, "secrets.json"), "utf8"), /postgresPassword/);
});

test("two generations never share a secret", () => {
  const [a, b] = [generateSecrets(), generateSecrets()];
  assert.notEqual(a.secretKey, b.secretKey);
  assert.notEqual(a.runtimePassword, a.postgresPassword);
});

test("the user's env file accepts provider settings and ignores everything else", () => {
  const parsed = parseUserEnv(['# comment', 'NEXUS_GEN_API_KEY="abc"', "export NEXUS_GEN_API_BASE='https://gw.example/v1'", "PATH=/evil", "lowercase=1", "NEXUS_OPENAI_API_KEY = spaced", "OPENAI_API_KEY=k"].join("\n"));
  assert.deepEqual(parsed, { NEXUS_GEN_API_KEY: "abc", NEXUS_GEN_API_BASE: "https://gw.example/v1", OPENAI_API_KEY: "k" });
});

test("a free port is free until something listens on it", async () => {
  const port = await freePort();
  assert.equal(await portInUse(port), false);
  const server = createServer();
  await new Promise<void>((done) => server.listen(port, "127.0.0.1", done));
  assert.equal(await portInUse(port), true);
  await new Promise((done) => server.close(done));
});

test("a line in the user's file cannot repoint the app's own database, queue or keys", () => {
  const user = parseUserEnv(["NEXUS_DB_HOST=evil", "NEXUS_REDIS_PASSWORD=x", "NEXUS_SECRET_KEY=x", "NEXUS_SANDBOX_PROVIDER=docker", "NEXUS_LOCAL_MODE=false", "NEXUS_PLUGIN_PATCHES=/tmp/x.yaml", "NEXUS_AUTOGEN_API_KEY=ok", "NEXUS_MODEL_RATES_JSON={}"].join("\n"));
  assert.deepEqual(allowedUserEnv(user), { NEXUS_AUTOGEN_API_KEY: "ok", NEXUS_MODEL_RATES_JSON: "{}" });
});
