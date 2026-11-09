"use client";

import { createContext, useContext } from "react";
import type { DockState, DockTab } from "@/lib/shell.mjs";
import type { ReviewState } from "@/components/workspace/use-review";
import type { Conversation } from "@/components/workspace/use-conversations";

export type NavPage = "studio" | "general" | "application" | "appearance" | "shortcuts" | "notifications" | "settings" | "integrations" | "teammates" | "intelligence";

/** What the parts of the shell need from each other: the right dock, navigation and the shortcut hints. */
export type ShellValue = {
  conversations: Conversation[];
  dock: DockState;
  showDock: (tab: DockTab) => void;
  toggleDock: () => void;
  closeDock: () => void;
  expandDock: () => void;
  navigate: (page: NavPage) => void;
  openPalette: () => void;
  hint: (action: string) => string;
  review: ReviewState;
  inspector: boolean;
  toggleInspector: () => void;
};

export const ShellContext = createContext<ShellValue | null>(null);

export function useShell(): ShellValue {
  const value = useContext(ShellContext);
  if (!value) throw new Error("useShell must be used inside the application shell");
  return value;
}
