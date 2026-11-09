import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { checkpointForStep, reviewSections, reviewedContent } from "../src/lib/artifact-review.mjs";
import { deliverableZip } from "../src/lib/deliverable-zip.mjs";

const before = 'title = "old"\nkeep = true\ntotal = 1\n';
const after = 'title = "new"\nkeep = true\ntotal = 2\n';

test("mixed hunk decisions preserve the original rejected section and final newline", () => {
  const changes = reviewSections(before, after).filter((section) => section.changed);
  assert.equal(changes.length, 2);
  assert.equal(reviewedContent(before, after, { [changes[0].id]: "accepted", [changes[1].id]: "rejected" }), 'title = "new"\nkeep = true\ntotal = 1\n');
  assert.equal(reviewedContent(before, after, {}), after);
  assert.equal(reviewedContent(before, after, Object.fromEntries(changes.map((section) => [section.id, "rejected"]))), before);
});

test("new files, deletion, empty text and replacement retain their exact content", () => {
  for (const [oldText, newText] of [[null, "a\nb\n"], ["a\nb\n", ""], ["", ""], ["hello", "goodbye"], ["a\r\nb\r\n", "a\r\nB\r\n"]]) {
    const ids = reviewSections(oldText, newText).filter((section) => section.changed).map((section) => section.id);
    assert.equal(reviewedContent(oldText, newText, {}), newText);
    assert.equal(reviewedContent(oldText, newText, Object.fromEntries(ids.map((id) => [id, "rejected"]))), oldText ?? "");
  }
});

test("restoring a step selects its own first completed checkpoint, never the newest unrelated one", () => {
  const rows = [{ id: "a", state: { completed_nodes: ["start", "first"] } }, { id: "b", state: { completed_nodes: ["start", "first", "second"] } }];
  assert.equal(checkpointForStep(rows, "first")?.id, "a");
  assert.equal(checkpointForStep(rows, "second")?.id, "b");
  assert.equal(checkpointForStep(rows, "unrecorded"), null);
});

test("ZIP round-trips unicode paths, binary media and CRCs through an independent reader", async () => {
  const blob = deliverableZip([{ name: "deliverables/báo-cáo.md", data: new TextEncoder().encode("Nexus ✓\n") }, { name: "media/video.mp4", data: Uint8Array.of(0, 255, 128, 1) }]);
  const result = execFileSync("python3", ["-c", "import io,json,sys,zipfile; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); print(json.dumps([z.testzip(),z.namelist(),z.read(z.namelist()[0]).decode(),list(z.read(z.namelist()[1]))]))"], { input: Buffer.from(await blob.arrayBuffer()) });
  assert.deepEqual(JSON.parse(result.toString()), [null, ["deliverables/báo-cáo.md", "media/video.mp4"], "Nexus ✓\n", [0, 255, 128, 1]]);
});

test("archive rejects traversal, absolute paths, normalized duplicates and control characters", () => {
  for (const name of ["../secret", "/etc/passwd", "C:/secret", "a/../secret", "a//b", "a/./b", "a\0b"]) assert.throws(() => deliverableZip([{ name, data: new Uint8Array() }]), /Unsafe/);
  assert.throws(() => deliverableZip([{ name: "a\\b", data: new Uint8Array() }, { name: "a/b", data: new Uint8Array() }]), /duplicate/);
});
