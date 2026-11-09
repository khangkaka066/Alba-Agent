import test from "node:test";
import assert from "node:assert/strict";
import { accountProvider, scopeId, shellQuote, loginScript } from "./account-login";
import { execFileSync } from "node:child_process";
test("only fixed providers and server-supplied UUID scopes can select a login profile", () => {
  assert.equal(accountProvider("codex"), "codex");
  for (const input of ["copilot", "codex; touch /tmp/attack", "../claude", null]) assert.throws(() => accountProvider(input));
  assert.equal(scopeId("EEA52D71-A77F-48E7-9AA1-20C4C940AF0A"), "eea52d71-a77f-48e7-9aa1-20c4c940af0a");
  for (const value of ["../workspace", "$(id)", "x\ny", null]) assert.throws(() => scopeId(value));
});
test("terminal arguments stay literal without evaluating renderer input", () => {
  const hostile = "a' b; $(printf leaked) `printf leaked` \" \\path";
  assert.equal(execFileSync("/bin/sh", ["-c", "printf %s " + shellQuote(hostile)], {encoding:"utf8"}), hostile);
  const script = loginScript(["/path with spaces/python", hostile]);
  assert.ok(script.startsWith("#!/bin/sh\nexec "));
  assert.equal(script.split("\n").length, 3);
});
