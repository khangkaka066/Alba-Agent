import type { ReactNode } from "react";

export type IconName =
  | "sidebar" | "back" | "forward" | "search" | "more" | "plus" | "filter" | "folder" | "folderPlus" | "chat" | "bolt" | "customize" | "settings"
  | "close" | "expand" | "collapse" | "mic" | "send" | "stop" | "copy" | "thumbUp" | "thumbDown" | "chevronDown" | "chevronRight" | "shield" | "globe"
  | "refresh" | "panelRight" | "review" | "file" | "terminal" | "extensions" | "canvas" | "trash" | "external" | "check" | "attach" | "log";

const PATHS: Record<IconName, ReactNode> = {
  sidebar: <><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><path d="M9.5 5v14" /></>,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  forward: <path d="M5 12h14M13 6l6 6-6 6" />,
  search: <><circle cx="10.8" cy="10.8" r="6.2" /><path d="m15.5 15.5 4.7 4.7" /></>,
  more: <path d="M12 6h.01M12 12h.01M12 18h.01" strokeWidth="2.6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  filter: <path d="M4 7h16M7 12h10M10 17h4" />,
  folder: <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />,
  folderPlus: <><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" /><path d="M12 10.5v5M9.5 13h5" /></>,
  chat: <><path d="M4 5.5h16v10.5H9l-4.5 3.5V5.5z" /></>,
  bolt: <path d="M13 3 5 13.5h6L10 21l8-10.5h-6z" />,
  customize: <><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /><path d="M16.75 4v6.5M13.5 7.25H20" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  expand: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  collapse: <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />,
  mic: <><rect x="9" y="3.5" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" /></>,
  send: <path d="M12 19V6M6.5 11.5 12 6l5.5 5.5" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="2" />,
  copy: <><rect x="8.5" y="8.5" width="11" height="11" rx="2" /><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" /></>,
  thumbUp: <path d="M8 11v8H5v-8zM8 11l3.2-6.2a1.8 1.8 0 0 1 3.3 1.3L13.8 9H19a1.8 1.8 0 0 1 1.7 2.3l-1.6 6.4a2 2 0 0 1-1.9 1.3H8" />,
  thumbDown: <path d="M8 13V5H5v8zM8 13l3.2 6.2a1.8 1.8 0 0 0 3.3-1.3L13.8 15H19a1.8 1.8 0 0 0 1.7-2.3l-1.6-6.4A2 2 0 0 0 17.2 5H8" />,
  chevronDown: <path d="m6 9 6 6 6-6" />,
  chevronRight: <path d="m9 6 6 6-6 6" />,
  shield: <path d="M12 3.5 19 6v5.5c0 4.2-2.8 7.2-7 9-4.2-1.8-7-4.8-7-9V6z" />,
  globe: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5S9.6 5.9 12 3.5z" /></>,
  refresh: <path d="M19.5 8A8 8 0 0 0 5.2 7.5M4.5 4v4h4M4.5 16a8 8 0 0 0 14.3.5M19.5 20v-4h-4" />,
  panelRight: <><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><path d="M14.5 5v14" /></>,
  review: <><path d="M6 3.5h8l4 4V20.5H6z" /><path d="M9.5 12h5M12 9.5v5" /></>,
  file: <path d="M6 3.5h8l4 4V20.5H6zM14 3.5v4h4" />,
  terminal: <><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><path d="m7.5 10 3 2.5-3 2.5M12.5 15h4" /></>,
  extensions: <path d="M10 4.5h4v3a1.5 1.5 0 1 0 3 0v-0M4.5 10h3a1.5 1.5 0 1 1 0 3h-3v6.5H11v-3a1.5 1.5 0 1 1 3 0v3h6.5V13h-3a1.5 1.5 0 1 1 0-3h3V4.5z" />,
  canvas: <><circle cx="6" cy="6.5" r="2.2" /><circle cx="18" cy="6.5" r="2.2" /><circle cx="12" cy="18" r="2.2" /><path d="M8 7.5l2.6 8.4M16 7.5l-2.6 8.4" /></>,
  trash: <path d="M5 7h14M10 7V4.5h4V7M7 7l.8 12h8.4L17 7M10.5 11v5M13.5 11v5" />,
  external: <path d="M14 4.5h5.5V10M19.5 4.5 11 13M17 14v4.5a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1H10" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  attach: <path d="m20 11-8 8a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L15 7" />,
  log: <path d="M5 6h14M5 10.5h14M5 15h9M5 19.5h6" />,
};

/** One icon set for the whole shell: 24px grid, 1.7 stroke, inherits the text colour. */
export function Icon({ name, size = 16, className = "" }: { name: IconName; size?: number; className?: string }) {
  return <svg className={`ag-icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PATHS[name]}</svg>;
}
