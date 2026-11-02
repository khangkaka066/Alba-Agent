// Social channels are only relevant to people whose teams publish: a team declares them in `modes.channels`.

export const CHANNEL_IDS = ["tiktok", "facebook", "youtube"];
export const CHANNEL_NAMES = { tiktok: "TikTok", facebook: "Facebook", youtube: "YouTube" };

const known = (value) => (Array.isArray(value) ? value.filter((item) => CHANNEL_IDS.includes(item)) : []);

/** Channels declared by one workflow spec, in display order. */
export function channelsOfSpec(spec) {
  const declared = known(spec && typeof spec === "object" ? spec.modes?.channels : []);
  return CHANNEL_IDS.filter((id) => declared.includes(id));
}

/** Channels any of the workspace's teams publish to. */
export function declaredChannels(workflows) {
  const wanted = new Set((Array.isArray(workflows) ? workflows : []).flatMap(channelsOfSpec));
  return CHANNEL_IDS.filter((id) => wanted.has(id));
}

/** The channels to show on the Tools page: those a team publishes to, plus any already connected so they stay manageable. */
export function visibleChannels(declared, connectedPresetIds) {
  const shown = new Set([...known(declared), ...known(connectedPresetIds)]);
  return CHANNEL_IDS.filter((id) => shown.has(id));
}

/** Declared channels that still lack a working connection, for the hint in the conversation. */
export function channelsToConnect(spec, credentials) {
  const connected = new Set((Array.isArray(credentials) ? credentials : []).filter((item) => item.status === "CONNECTED").map((item) => item.preset_id));
  return channelsOfSpec(spec).filter((id) => !connected.has(id));
}

export const channelList = (ids) => ids.map((id) => CHANNEL_NAMES[id]).join(", ");
