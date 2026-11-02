import test from "node:test";
import assert from "node:assert/strict";
import { billingLabel, expiryLabel, groupDeviceCode, mountedSummary, nextPollSeconds, verifySummary } from "../src/lib/subscriptions.mjs";

const now = Date.parse("2026-11-01T12:00:00Z");

test("expiry reads as minutes, hours or days and flags expired logins", () => {
  assert.equal(expiryLabel(null, now), "");
  assert.equal(expiryLabel("2026-11-01T11:00:00Z", now), "expired");
  assert.equal(expiryLabel("2026-11-01T12:20:00Z", now), "expires in 20 min");
  assert.equal(expiryLabel("2026-11-01T17:00:00Z", now), "expires in 5 h");
  assert.equal(expiryLabel("2026-11-11T12:00:00Z", now), "expires in 10 days");
});

test("a connector card explains what the mount holds without exposing anything secret", () => {
  assert.equal(mountedSummary({ enabled: false, found: false }).tone, "off");
  assert.equal(mountedSummary({ enabled: true, found: false }).tone, "none");
  assert.deepEqual(mountedSummary({ enabled: true, found: true, valid: false, error: "The Claude session has expired" }), { tone: "bad", text: "The Claude session has expired" });
  assert.equal(mountedSummary({ enabled: true, found: true, valid: true, plan: "plus", expires_at: null }).text, "Detected plus plan");
});

test("device login polling honours the interval and backs off on slow_down", () => {
  assert.equal(nextPollSeconds(5, "pending"), 5);
  assert.equal(nextPollSeconds(undefined, "pending"), 5);
  assert.equal(nextPollSeconds(5, "slow_down", 10), 10);
  assert.equal(nextPollSeconds(5, "slow_down"), 10);
});

test("the 8-character device code is grouped for reading aloud", () => {
  assert.equal(groupDeviceCode("wdjbmjht"), "WDJB-MJHT");
  assert.equal(groupDeviceCode("WDJB-MJHT"), "WDJB-MJHT");
  assert.equal(groupDeviceCode("abc"), "abc");
});

test("billing and verification wording separates plan usage from metered usage", () => {
  assert.match(billingLabel({ billing_mode: "SUBSCRIPTION_INCLUDED" }), /\$0 per token/);
  assert.equal(billingLabel({}), "Metered per token");
  assert.equal(verifySummary(null), null);
  assert.equal(verifySummary({ ok: true, status: "CONNECTED", model: "gpt-4.1", latency_ms: 812, billing_mode: "SUBSCRIPTION_INCLUDED", cost_usd: "0", reply: "OK", error: null })?.text, "gpt-4.1 answered in 812 ms · included in plan");
  assert.deepEqual(verifySummary({ ok: false, status: "ERROR", model: "m", latency_ms: 1, billing_mode: "", cost_usd: "0", reply: "", error: "The plan rejected the credential." }), { tone: "bad", text: "The plan rejected the credential." });
});
