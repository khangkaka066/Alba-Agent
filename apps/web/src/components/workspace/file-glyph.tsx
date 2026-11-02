import type { ArtifactKind } from "@/lib/workspace.mjs";

const SHAPES: Record<ArtifactKind | "dir", React.ReactNode> = {
  dir: <path d="M3.5 6.5h6l1.8 2H20.5v9.5h-17z" />,
  code: <><path d="m9 8-4 4 4 4M15 8l4 4-4 4" /></>,
  document: <><path d="M6 3.5h8l4 4v13H6z" /><path d="M9 12h6M9 16h6" /></>,
  image: <><rect x="4" y="5" width="16" height="14" rx="1.5" /><circle cx="9" cy="10" r="1.5" /><path d="m5 17 5-4 3 2.5 3-3 3 3.5" /></>,
  video: <><rect x="4" y="6" width="12" height="12" rx="1.5" /><path d="m16 10.5 4-2.5v8l-4-2.5z" /></>,
  audio: <path d="M5 10v4M9 7v10M13 9v6M17 6v12" />,
  pdf: <><path d="M6 3.5h8l4 4v13H6z" /><path d="M9 15.5h6" /></>,
  other: <><path d="M6 3.5h8l4 4v13H6z" /></>,
};

export function FileGlyph({ kind }: { kind: ArtifactKind | "dir" }) {
  return <svg className={`file-glyph file-glyph--${kind}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{SHAPES[kind]}</svg>;
}
