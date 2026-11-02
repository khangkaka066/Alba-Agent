import assert from "node:assert/strict";
import test from "node:test";
import { channelList, channelsOfSpec, channelsToConnect, declaredChannels, visibleChannels } from "../src/lib/channels.mjs";

const film = { modes: { rigor: "full_studio", channels: ["youtube", "tiktok", "facebook"] } };

test("a team's channels come back in display order and unknown ones are ignored", () => {
  assert.deepEqual(channelsOfSpec(film), ["tiktok", "facebook", "youtube"]);
  assert.deepEqual(channelsOfSpec({ modes: { channels: ["myspace", "tiktok"] } }), ["tiktok"]);
  for (const nothing of [null, undefined, {}, { modes: {} }, { modes: { channels: "tiktok" } }, "text"]) assert.deepEqual(channelsOfSpec(nothing), []);
});

test("channels are only declared when some team in the workspace publishes", () => {
  assert.deepEqual(declaredChannels([{ modes: { rigor: "standard" } }, { name: "csv report" }]), []);
  assert.deepEqual(declaredChannels([{ modes: { channels: ["youtube"] } }, { modes: { channels: ["tiktok"] } }]), ["tiktok", "youtube"]);
  assert.deepEqual(declaredChannels(undefined), []);
});

test("the Tools page shows declared channels plus ones already connected, and nothing otherwise", () => {
  assert.deepEqual(visibleChannels([], []), []);
  assert.deepEqual(visibleChannels(["tiktok"], []), ["tiktok"]);
  assert.deepEqual(visibleChannels([], ["youtube", "openai"]), ["youtube"]);
  assert.deepEqual(visibleChannels(["facebook"], ["tiktok"]), ["tiktok", "facebook"]);
});

test("the hint lists only the declared channels that are not connected yet", () => {
  const saved = [{ preset_id: "tiktok", status: "CONNECTED" }, { preset_id: "youtube", status: "ERROR" }, { preset_id: "openai", status: "CONNECTED" }];
  assert.deepEqual(channelsToConnect(film, saved), ["facebook", "youtube"]);
  assert.deepEqual(channelsToConnect(film, []), ["tiktok", "facebook", "youtube"]);
  assert.deepEqual(channelsToConnect({ modes: {} }, []), []);
  assert.equal(channelList(["tiktok", "youtube"]), "TikTok, YouTube");
});
