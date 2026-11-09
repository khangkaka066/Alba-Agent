export type MarkdownBlock =
  | { kind: "code"; language: string; text: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "rule" }
  | { kind: "table"; headers: string[]; rows: string[][] }
  | { kind: "quote" | "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; start: number; items: string[] };
export function safeLink(value: string): string | null;
export function markdownBlocks(text: string): MarkdownBlock[];
