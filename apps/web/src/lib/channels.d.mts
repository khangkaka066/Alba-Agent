export type ChannelId = "tiktok" | "facebook" | "youtube";
export const CHANNEL_IDS: ChannelId[];
export const CHANNEL_NAMES: Record<ChannelId, string>;
export function channelsOfSpec(spec: unknown): ChannelId[];
export function declaredChannels(workflows: unknown): ChannelId[];
export function visibleChannels(declared: unknown, connectedPresetIds: unknown): ChannelId[];
export function channelsToConnect(spec: unknown, credentials: unknown): ChannelId[];
export function channelList(ids: ChannelId[]): string;
