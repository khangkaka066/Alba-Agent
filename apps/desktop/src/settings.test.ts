import assert from "node:assert/strict";
import test from "node:test";
import { resolveWebUrl } from "./settings";

test("the window connects to a local stack or an HTTPS server, never plain HTTP on the internet", () => {
  assert.equal(resolveWebUrl(undefined, undefined), "http://localhost:3000");
  assert.equal(resolveWebUrl("https://studio.example.com/app", undefined), "https://studio.example.com");
  assert.equal(resolveWebUrl("http://studio.example.com", "http://127.0.0.1:3100"), "http://127.0.0.1:3100");
  assert.equal(resolveWebUrl("not a url", "https://saved.example.com"), "https://saved.example.com");
  assert.equal(resolveWebUrl("javascript:alert(1)", undefined), "http://localhost:3000");
});
