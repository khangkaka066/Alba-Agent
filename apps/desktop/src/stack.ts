// Starts everything NexusAgent needs on this machine, with no Docker: Postgres, Redis, Qdrant, the API, the worker and the web server.
// They are the same services docker-compose runs, shipped as binaries inside the app (see scripts/package/build_runtime.py), so the
// application code and its behaviour are the ones that were measured. This file does not import Electron: the app wraps it, and
// `stack-cli.ts` runs it headless for smoke tests.
import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer, connect } from "node:net";
import { join, resolve } from "node:path";

export interface Secrets {
  postgresPassword: string;
  runtimePassword: string;
  redisPassword: string;
  secretKey: string;
  apiKeyPepper: string;
  encryptionKeyBase64: string;
}

export interface Ports {
  api: number;
  web: number;
  postgres: number;
  redis: number;
  qdrant: number;
  qdrantGrpc: number;
}

export interface StackOptions {
  runtime: string; // the folder build_runtime.py produced
  data: string; // per-user data folder (database files, secrets, computers)
  executable: string; // a Node-compatible binary for the web server (Electron's own with ELECTRON_RUN_AS_NODE, or node)
  onStatus?: (message: string) => void;
  onLog?: (service: string, line: string) => void;
}

const SECRET_NAMES = ["postgresPassword", "runtimePassword", "redisPassword", "secretKey", "apiKeyPepper", "encryptionKeyBase64"] as const;

export function generateSecrets(): Secrets {
  const token = (): string => randomBytes(24).toString("base64url"); // URL-safe: these end up inside connection URLs
  return {
    postgresPassword: token(), runtimePassword: token(), redisPassword: token(), secretKey: randomBytes(32).toString("base64url"),
    apiKeyPepper: randomBytes(32).toString("base64url"), encryptionKeyBase64: randomBytes(32).toString("base64"),
  };
}

// Generated once and kept: a new password would lock the user out of the existing database, a new encryption key out of stored credentials.
export function loadOrCreateSecrets(data: string): Secrets {
  const file = join(data, "secrets.json");
  mkdirSync(data, { recursive: true, mode: 0o700 });
  if (existsSync(file)) {
    const parsed = JSON.parse(readFileSync(file, "utf8")) as Partial<Secrets>;
    if (SECRET_NAMES.every((name) => typeof parsed[name] === "string" && parsed[name] !== "")) return parsed as Secrets;
    throw new Error(`${file} is incomplete; restore it from a backup rather than regenerating (that would lock the existing data)`);
  }
  const secrets = generateSecrets();
  writeFileSync(file, JSON.stringify(secrets, null, 2), { mode: 0o600 });
  chmodSync(file, 0o600);
  return secrets;
}

// `KEY=value` lines the user can add (model gateway keys, base URLs). Anything that is not a plain NEXUS_/provider variable is ignored.
export function parseUserEnv(text: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const match = /^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$/.exec(line);
    if (!match?.[1]) continue;
    let value = (match[2] ?? "").trim();
    if (value.length >= 2 && ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'")))) value = value.slice(1, -1);
    if (/^(NEXUS_|OPENAI_|ANTHROPIC_|LITELLM_)/.test(match[1])) result[match[1]] = value;
  }
  return result;
}

// Variables the app itself decides. A line in the user's file must never override them (a wrong database host would be a silent break).
const RESERVED = /^NEXUS_(DB_|REDIS_|QDRANT_|MIGRATION_|SETUP_|DATABASE_|SECRET_KEY|API_KEY_PEPPER|CREDENTIAL_|ENCRYPTION_|SANDBOX_|COMPUTER_ROOT|LOCAL_MODE|PLUGIN_PATCHES|ARTIFACTS_DIR|SUBSCRIPTIONS_DIR|RELOAD)/;

export function allowedUserEnv(user: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(user).filter(([key]) => !RESERVED.test(key)));
}

export function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => (typeof address === "object" && address ? resolve(address.port) : reject(new Error("no port"))));
    });
  });
}

export function portInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = connect({ port, host: "127.0.0.1" });
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("error", () => resolve(false));
  });
}

async function waitFor(check: () => Promise<boolean>, what: string, seconds: number, failure: () => Error | undefined = () => undefined): Promise<void> {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    const broken = failure();
    if (broken) throw broken;
    if (await check().catch(() => false)) return;
    await new Promise((done) => setTimeout(done, 250));
  }
  throw new Error(`${what} did not become ready within ${seconds} s`);
}

const httpOk = async (url: string): Promise<boolean> => (await fetch(url, { signal: AbortSignal.timeout(2000) })).ok;
const tcpOpen = async (port: number): Promise<boolean> => portInUse(port);

export interface Layout {
  python: string; postgresBin: (name: string) => string; redis: string; qdrant: string; backend: string; web: string;
  apiPort: number; webPort: number;
}

export function layoutFor(runtime: string): Layout {
  const manifest = JSON.parse(readFileSync(join(runtime, "manifest.json"), "utf8")) as { pins: { ports: { api: number; web: number } } };
  return {
    python: join(runtime, "python", "bin", "python3"),
    postgresBin: (name) => join(runtime, "postgres", "bin", name),
    redis: join(runtime, "redis", "redis-server"),
    qdrant: join(runtime, "qdrant", "qdrant"),
    backend: join(runtime, "backend"),
    web: join(runtime, "web", "apps", "web", "server.js"),
    apiPort: manifest.pins.ports.api, webPort: manifest.pins.ports.web,
  };
}

// Programs that run to the end by design; their exit is not a failure.
const oneShot = new Set(["initdb", "bootstrap", "migrate"]);

export class Stack {
  private readonly children = new Map<string, ChildProcess>();
  private stopping = false;
  private failed: Error | undefined;
  private secrets!: Secrets;
  private ports!: Ports;
  private layout: Layout;

  private readonly options: StackOptions;

  constructor(options: StackOptions) {
    // macOS only for now: the sandbox (Seatbelt), the process-group handling and the Postgres locale below are written for it. A Windows
    // build needs its own sandbox first; see tasks/todo.md, Phase 36.
    if (process.platform !== "darwin") throw new Error("The embedded stack is available on macOS only");
    this.options = { ...options, runtime: resolve(options.runtime), data: resolve(options.data) }; // children run in other folders, so relative paths would break
    this.layout = layoutFor(this.options.runtime);
  }

  get webUrl(): string { return `http://127.0.0.1:${this.layout.webPort}`; }
  get apiUrl(): string { return `http://127.0.0.1:${this.layout.apiPort}`; }

  private failure(): Error | undefined { return this.failed ?? (this.stopping ? new Error("The app is closing") : undefined); }

  private status(message: string): void { this.options.onStatus?.(message); }
  private dir(...parts: string[]): string { const path = join(this.options.data, ...parts); mkdirSync(path, { recursive: true, mode: 0o700 }); return path; }

  private baseEnvironment(): NodeJS.ProcessEnv {
    // The host environment is not passed on: it may hold unrelated tokens. Only what a child needs to find its own libraries.
    const keep = ["PATH", "TMPDIR", "HOME", "LANG", "LC_ALL"];
    const environment: NodeJS.ProcessEnv = {};
    for (const key of keep) if (process.env[key] !== undefined) environment[key] = process.env[key];
    return environment;
  }

  private backendEnvironment(): NodeJS.ProcessEnv {
    const { secrets, ports, layout } = this;
    const databaseUrl = `postgresql+asyncpg://nexus:${secrets.postgresPassword}@127.0.0.1:${ports.postgres}/nexus`;
    const packages = ["core-schema/python", "core-schema/templates", "model-gateway", "agent-runtime", "learning-transfer", "computer-sandbox", "rag-engine", "mcp-hub", "agent-skills", "builtin-tools"];
    const userFile = join(this.options.data, "nexus.env");
    const user = existsSync(userFile) ? parseUserEnv(readFileSync(userFile, "utf8")) : {};
    const allowedUser = allowedUserEnv(user);
    return {
      ...this.baseEnvironment(), ...allowedUser,
      NEXUS_BRAND_NAME: "NexusAgent Studio",
      NEXUS_CORS_ORIGINS: `http://127.0.0.1:${layout.webPort},http://localhost:${layout.webPort}`,
      NEXUS_DB_HOST: "127.0.0.1", NEXUS_DB_PORT: String(ports.postgres), NEXUS_DB_NAME: "nexus", NEXUS_DB_USER: "nexus_runtime", NEXUS_DB_PASSWORD: secrets.runtimePassword,
      NEXUS_MIGRATION_DATABASE_URL: databaseUrl, NEXUS_SETUP_DATABASE_URL: databaseUrl,
      NEXUS_REDIS_HOST: "127.0.0.1", NEXUS_REDIS_PORT: String(ports.redis), NEXUS_REDIS_PASSWORD: secrets.redisPassword,
      NEXUS_QDRANT_URL: `http://127.0.0.1:${ports.qdrant}`,
      NEXUS_SECRET_KEY: secrets.secretKey, NEXUS_API_KEY_PEPPER: secrets.apiKeyPepper, NEXUS_CREDENTIAL_ENCRYPTION_KEY_BASE64: secrets.encryptionKeyBase64,
      NEXUS_SANDBOX_URL: `${this.apiUrl}/api/v1/sandboxes`, NEXUS_SANDBOX_PROVIDER: "local",
      NEXUS_COMPUTER_ROOT: this.dir("computers"), NEXUS_ARTIFACTS_DIR: this.dir("artifacts"), NEXUS_SUBSCRIPTIONS_DIR: this.dir("subscriptions"),
      NEXUS_LOCAL_MODE: "true", NEXUS_RELOAD: "false",
      NEXUS_PLUGIN_PATCHES: join(layout.backend, "packages", "agent-runtime", "nexus_plugins", "local-mode.yaml"),
      PYTHONPATH: [join(layout.backend, "apps", "api"), ...packages.map((name) => join(layout.backend, "packages", name))].join(":"),
      PYTHONDONTWRITEBYTECODE: "1", PYTHONNOUSERSITE: "1", PYTHONUNBUFFERED: "1",
      OTEL_SDK_DISABLED: "true", CREWAI_DISABLE_TELEMETRY: "true", ANONYMIZED_TELEMETRY: "false", DO_NOT_TRACK: "true", LITELLM_TELEMETRY_DISABLED: "true", LITELLM_OFFLINE_MODE: "true",
    };
  }

  private spawnService(name: string, command: string, args: string[], environment: NodeJS.ProcessEnv, cwd?: string): ChildProcess {
    if (this.stopping) throw new Error("The app is closing"); // quitting while still starting must not leave new processes behind
    const child = spawn(command, args, { env: environment, cwd, stdio: ["ignore", "pipe", "pipe"], detached: true });
    const forward = (chunk: Buffer): void => { for (const line of chunk.toString("utf8").split(/\r?\n/)) if (line.trim()) this.options.onLog?.(name, line); };
    child.stdout?.on("data", forward);
    child.stderr?.on("data", forward);
    child.once("exit", (code, signal) => {
      this.children.delete(name);
      if (!this.stopping && !oneShot.has(name)) this.options.onLog?.(name, `exited unexpectedly (code ${code ?? "none"}, signal ${signal ?? "none"})`);
    });
    child.once("error", (error) => { this.options.onLog?.(name, `could not start: ${error.message}`); this.failed ??= new Error(`${name} could not start: ${error.message}`); });
    this.children.set(name, child);
    this.recordPids(); // written as each child starts, so a failed start does not leave processes nobody knows about
    return child;
  }

  private async runToEnd(name: string, command: string, args: string[], environment: NodeJS.ProcessEnv, cwd?: string): Promise<void> {
    const child = this.spawnService(name, command, args, environment, cwd);
    const tail: string[] = [];
    const remember = (chunk: Buffer): void => { tail.push(...chunk.toString("utf8").split(/\r?\n/).filter(Boolean)); tail.splice(0, Math.max(0, tail.length - 12)); };
    child.stdout?.on("data", remember);
    child.stderr?.on("data", remember);
    const code = await new Promise<number | null>((done) => child.once("exit", done));
    if (code !== 0) throw new Error(`${name} failed (exit ${code}):\n${tail.join("\n")}`);
  }

  // The start time of a process, which identifies it better than its command line: the web server renames itself ("next-server") and a pid
  // alone can be reused by another program after a crash.
  private startedAt(pid: number): string {
    return (spawnSync("ps", ["-p", String(pid), "-o", "lstart="], { encoding: "utf8" }).stdout ?? "").trim();
  }

  // A previous run that was killed leaves children behind; they hold the data folder locked and the ports. Only processes that were
  // started by this app (same pid and same start time) are stopped.
  private stopStale(): void {
    const file = join(this.options.data, "run.pids");
    if (!existsSync(file)) return;
    for (const entry of readFileSync(file, "utf8").split("\n").filter(Boolean)) {
      const [pid, ...rest] = entry.split("\t");
      const id = Number(pid);
      if (!Number.isInteger(id) || id <= 0 || rest.length === 0) continue;
      const started = this.startedAt(id);
      if (!started || started !== rest.join("\t")) continue; // gone, or the pid now belongs to something else
      try { process.kill(-id, "SIGKILL"); } catch { /* already gone */ }
    }
    rmSync(file, { force: true });
  }

  private recordPids(): void {
    const lines = [...this.children.values()].filter((child) => child.pid).map((child) => `${child.pid}\t${this.startedAt(child.pid as number)}`);
    writeFileSync(join(this.options.data, "run.pids"), lines.join("\n") + "\n", { mode: 0o600 });
  }

  private starting: Promise<void> | undefined;

  start(): Promise<void> {
    this.starting = this.run();
    return this.starting;
  }

  private async run(): Promise<void> {
    const { layout, options } = this;
    mkdirSync(options.data, { recursive: true, mode: 0o700 });
    this.stopStale();
    for (const port of [layout.apiPort, layout.webPort]) {
      // Processes just stopped above need a moment to release their sockets.
      const deadline = Date.now() + 10_000;
      while ((await portInUse(port)) && Date.now() < deadline) await new Promise((done) => setTimeout(done, 200));
      if (await portInUse(port)) throw new Error(`Port ${port} is already in use by another program. Close it and start NexusAgent again.`);
    }
    this.secrets = loadOrCreateSecrets(options.data);
    this.ports = { api: layout.apiPort, web: layout.webPort, postgres: await freePort(), redis: await freePort(), qdrant: await freePort(), qdrantGrpc: await freePort() };
    const base = this.baseEnvironment();

    this.status("Starting the database…");
    const pgData = join(options.data, "postgres");
    if (!existsSync(join(pgData, "PG_VERSION"))) {
      const pwfile = join(options.data, ".pgpass-init");
      writeFileSync(pwfile, this.secrets.postgresPassword, { mode: 0o600 });
      try {
        // The Docker image's default locale is en_US.utf8; keep it so text ordering matches what was tested.
        await this.runToEnd("initdb", layout.postgresBin("initdb"), ["-D", pgData, "-U", "nexus", "--auth=scram-sha-256", `--pwfile=${pwfile}`, "-E", "UTF8", "--locale=en_US.UTF-8"], base);
      } finally { rmSync(pwfile, { force: true }); }
    }
    this.spawnService("postgres", layout.postgresBin("postgres"), ["-D", pgData, "-p", String(this.ports.postgres), "-c", "listen_addresses=127.0.0.1", "-c", "unix_socket_directories=", "-c", "fsync=on"], base);
    await waitFor(() => tcpOpen(this.ports.postgres), "Postgres", 60, () => this.failure());

    this.status("Starting Redis and Qdrant…");
    const redisDir = this.dir("redis");
    const redisConfig = join(redisDir, "redis.conf");
    writeFileSync(redisConfig, `bind 127.0.0.1\nport ${this.ports.redis}\nrequirepass ${this.secrets.redisPassword}\nappendonly yes\ndir ${redisDir.replace(/\\/g, "/")}\nsave ""\n`, { mode: 0o600 });
    this.spawnService("redis", layout.redis, [redisConfig], base);
    this.spawnService("qdrant", layout.qdrant, [], { ...base, QDRANT__SERVICE__HOST: "127.0.0.1", QDRANT__SERVICE__HTTP_PORT: String(this.ports.qdrant), QDRANT__SERVICE__GRPC_PORT: String(this.ports.qdrantGrpc), QDRANT__STORAGE__STORAGE_PATH: this.dir("qdrant"), QDRANT__STORAGE__SNAPSHOTS_PATH: this.dir("qdrant-snapshots"), QDRANT__TELEMETRY_DISABLED: "true" }, options.data);
    await Promise.all([waitFor(() => tcpOpen(this.ports.redis), "Redis", 30, () => this.failure()), waitFor(() => httpOk(`http://127.0.0.1:${this.ports.qdrant}/readyz`), "Qdrant", 60, () => this.failure())]);

    this.status("Preparing the database…");
    const environment = this.backendEnvironment();
    await this.runToEnd("bootstrap", layout.python, [join(layout.backend, "bootstrap_database.py")], { ...environment, NEXUS_RUNTIME_DB_PASSWORD: this.secrets.runtimePassword }, layout.backend);
    await this.runToEnd("migrate", layout.python, ["-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"], { ...environment, NEXUS_DATABASE_URL: environment.NEXUS_MIGRATION_DATABASE_URL }, layout.backend);

    this.status("Starting NexusAgent…");
    const { NEXUS_MIGRATION_DATABASE_URL: _migration, NEXUS_SETUP_DATABASE_URL: _setup, ...workerEnvironment } = environment;
    this.spawnService("api", layout.python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(layout.apiPort), "--proxy-headers"], environment, layout.backend);
    this.spawnService("worker", layout.python, ["-m", "celery", "-A", "app.workers.jobs:celery_app", "worker", "--loglevel=INFO", "--pool=threads", `--concurrency=${environment.NEXUS_WORKER_CONCURRENCY ?? "2"}`], workerEnvironment, layout.backend);
    this.spawnService("web", options.executable, [layout.web], { ...base, ELECTRON_RUN_AS_NODE: "1", NODE_ENV: "production", PORT: String(layout.webPort), HOSTNAME: "127.0.0.1", NEXUS_API_INTERNAL_URL: this.apiUrl, NEXT_TELEMETRY_DISABLED: "1" }, join(options.runtime, "web", "apps", "web"));
    this.recordPids();
    await waitFor(() => httpOk(`${this.apiUrl}/ready`), "The API", 120, () => this.failure());
    await waitFor(() => httpOk(`${this.webUrl}/`), "The web app", 60, () => this.failure());
    this.status("Ready");
  }

  async stop(): Promise<void> {
    this.stopping = true;
    await this.starting?.catch(() => undefined); // let a start in progress notice and unwind before the children are counted
    // Reverse order of start: the clients go first so nothing is writing when the database stops.
    const order = ["web", "worker", "api", "qdrant", "redis", "postgres"];
    for (const name of [...[...this.children.keys()].filter((key) => !order.includes(key)), ...order]) { // one-shot steps (migrate...) first
      const child = this.children.get(name);
      if (!child?.pid) continue;
      const exited = new Promise<void>((done) => child.once("exit", () => done()));
      try { process.kill(-child.pid, name === "postgres" ? "SIGINT" : "SIGTERM"); } catch { /* gone */ }
      await Promise.race([exited, new Promise<void>((done) => setTimeout(done, name === "postgres" ? 20000 : 8000))]);
      if (this.children.has(name)) { try { process.kill(-child.pid, "SIGKILL"); } catch { /* gone */ } }
    }
    rmSync(join(this.options.data, "run.pids"), { force: true });
  }
}
