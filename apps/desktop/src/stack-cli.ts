// Runs the packaged stack without Electron: `node dist/stack-cli.js <runtime dir> <data dir>`. Used for smoke tests and CI; prints the web
// address once everything answers, then waits for SIGINT/SIGTERM and shuts the services down in order.
import { Stack } from "./stack";

const [runtime, data] = process.argv.slice(2);
if (!runtime || !data) {
  console.error("usage: stack-cli <runtime dir> <data dir>");
  process.exit(64);
}
const stack = new Stack({ runtime, data, executable: process.execPath, onStatus: (message) => console.log(`[status] ${message}`), onLog: (service, line) => { if (process.env.NEXUS_STACK_VERBOSE) console.log(`[${service}] ${line}`); } });
let closing = false;
const close = (): void => { if (closing) return; closing = true; void stack.stop().then(() => process.exit(0)); };
process.on("SIGINT", close);
process.on("SIGTERM", close);
stack.start().then(() => console.log(`[ready] ${stack.webUrl} api ${stack.apiUrl}`)).catch((error: unknown) => { console.error(`[failed] ${error instanceof Error ? error.message : String(error)}`); void stack.stop().then(() => process.exit(1)); });
