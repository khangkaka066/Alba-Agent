"use client";

import { useEffect, useState } from "react";
import { classifyArtifact, diffStats, lineDiff } from "@/lib/workspace.mjs";
import { reviewTotals } from "@/lib/shell.mjs";
import { useWorkspace } from "./workspace-context";

export type ReviewFile = { filename: string; added: number; removed: number; fresh: boolean; text: boolean; sizeBytes: number };
export type ReviewState = { ready: boolean; files: ReviewFile[]; totals: { added: number; removed: number } };

const LIMIT = 40; // a task with more files than this is summarised by its first files; the rest stay reachable in the file list

/** Lines added and removed in every file the agent produced, measured against the version it replaced (or against nothing for a new file). */
export function useReview(): ReviewState {
  const { artifacts, fetchArtifact, beforeText, runId } = useWorkspace();
  const [state, setState] = useState<ReviewState>({ ready: true, files: [], totals: { added: 0, removed: 0 } });
  const signature = artifacts.map((item) => `${item.filename}:${item.size_bytes}`).join("|");
  useEffect(() => {
    if (artifacts.length === 0) { setState({ ready: true, files: [], totals: { added: 0, removed: 0 } }); return; }
    let stopped = false;
    setState((current) => ({ ...current, ready: false }));
    void (async () => {
      const files: ReviewFile[] = [];
      for (const artifact of artifacts.slice(0, LIMIT)) {
        const text = classifyArtifact(artifact.filename, artifact.mime_type).text;
        let added = 0; let removed = 0; let fresh = true;
        if (text) {
          try {
            const after = await fetchArtifact(artifact, "text");
            const before = await beforeText(artifact.filename).catch(() => null);
            if (typeof after === "string") { const stats = diffStats(lineDiff(before ?? "", after)); added = stats.added; removed = stats.removed; fresh = before === null; }
          } catch { /* a file that cannot be read is listed without figures */ }
        }
        if (stopped) return;
        files.push({ filename: artifact.filename, added, removed, fresh, text: Boolean(text), sizeBytes: artifact.size_bytes });
      }
      if (!stopped) setState({ ready: true, files, totals: reviewTotals(files) });
    })();
    return () => { stopped = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `signature` stands for the artifact list; the callbacks change identity on every render
  }, [signature, runId]);
  return state;
}
