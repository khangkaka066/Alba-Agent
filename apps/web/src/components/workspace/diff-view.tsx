"use client";

import { useMemo } from "react";
import { diffStats, lineDiff, splitRows, type DiffOp } from "@/lib/workspace.mjs";

function Cell({ op, side }: { op: DiffOp | null; side: "left" | "right" }) {
  if (!op) return <><span className="diff-no" /><code className="diff-code diff-code--empty" /></>;
  const tone = op.type === "same" ? "" : side === "left" ? "diff-code--del" : "diff-code--add";
  return <><span className="diff-no">{side === "left" ? op.oldNo : op.newNo}</span><code className={`diff-code ${tone}`}>{op.text || " "}</code></>;
}

/** Side-by-side line diff. With no earlier version the file is shown as a single "new file" listing. */
export function DiffView({ before, after, filename }: { before: string | null; after: string; filename: string }) {
  const ops = useMemo(() => lineDiff(before ?? "", after), [before, after]);
  const rows = useMemo(() => splitRows(ops), [ops]);
  const stats = diffStats(ops);
  const fresh = before === null;
  return <div className="diff-view" aria-label={`Changes in ${filename}`}>
    <div className="diff-summary"><span className="diff-stat diff-stat--add">+{stats.added}</span><span className="diff-stat diff-stat--del">−{stats.removed}</span><span>{fresh ? "New file" : stats.added + stats.removed === 0 ? "No changes" : "Changed lines"}</span></div>
    {fresh
      ? <div className="diff-grid diff-grid--single">{after.split("\n").map((line, index) => <div className="diff-row" key={index}><span className="diff-no">{index + 1}</span><code className="diff-code diff-code--add">{line || " "}</code></div>)}</div>
      : <div className="diff-grid"><div className="diff-heads"><span>Before</span><span>After</span></div>
        {rows.map((row, index) => <div className="diff-row diff-row--split" key={index}><Cell op={row.left} side="left" /><Cell op={row.right} side="right" /></div>)}</div>}
  </div>;
}
