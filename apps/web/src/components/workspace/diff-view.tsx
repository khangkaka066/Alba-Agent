"use client";

import { useMemo, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { diffStats, splitRows, type DiffOp } from "@/lib/workspace.mjs";
import { reviewSections, type HunkDecision } from "@/lib/artifact-review.mjs";

/** A small lexer keeps syntax legible without running or interpreting artifact contents. */
function Syntax({ text, filename }: { text: string; filename: string }) {
  const code = /\.(?:[cm]?[jt]sx?|py|json|ya?ml|toml|sh|css|html|sql)$/i.test(filename);
  if (!code) return <>{text || " "}</>;
  const tokens = text.split(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\/\/.*$|#.*$|\b(?:const|let|var|function|return|import|from|export|default|async|await|class|def|if|else|for|in|True|False|true|false|null|None|type|interface)\b|\b\d+(?:\.\d+)?\b)/g);
  return <>{tokens.map((token, index) => <span key={index} className={/^["']/.test(token) ? "syntax-string" : /^(?:#|\/\/)/.test(token) ? "syntax-comment" : /^\d/.test(token) ? "syntax-number" : /^(?:const|let|var|function|return|import|from|export|default|async|await|class|def|if|else|for|in|True|False|true|false|null|None|type|interface)$/.test(token) ? "syntax-keyword" : undefined}>{token}</span>)}</>;
}

function Cell({ op, side, filename }: { op: DiffOp | null; side: "left" | "right"; filename: string }) {
  if (!op) return <><span className="diff-no" /><code className="diff-code diff-code--empty" /></>;
  const tone = op.type === "same" ? "" : side === "left" ? "diff-code--del" : "diff-code--add";
  return <><span className="diff-no">{side === "left" ? op.oldNo : op.newNo}</span><code className={`diff-code ${tone}`}><Syntax text={op.text} filename={filename} /></code></>;
}

/** Hunk decisions are owned by the workspace; changing tabs cannot discard the review. */
export function DiffView({ before, after, filename, decisions = {}, onDecision }: { before: string | null; after: string; filename: string; decisions?: Record<string, HunkDecision>; onDecision?: (id: string, decision: HunkDecision) => void }) {
  const { t } = useLocale();
  const [layout, setLayout] = useState<"split" | "unified">("split");
  const [focused, setFocused] = useState<string | null>(null);
  const sections = useMemo(() => reviewSections(before, after), [before, after]);
  const stats = diffStats(sections.flatMap((section) => section.ops));
  return <div className="diff-view ag-interactive-diff" tabIndex={0} aria-label={t("studio.changesIn", { filename })} onKeyDown={(event) => {
    if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.altKey || !onDecision || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) return;
    const key = event.key.toLowerCase();
    const target = focused ?? sections.find((section) => section.changed && !decisions[section.id])?.id;
    if (target && ["y", "n"].includes(key)) { event.preventDefault(); event.stopPropagation(); onDecision(target, key === "y" ? "accepted" : "rejected"); }
  }}>
    <div className="diff-summary"><span className="diff-stat diff-stat--add">+{stats.added}</span><span className="diff-stat diff-stat--del">−{stats.removed}</span><span>{t(before === null ? "stage.new" : "studio.changedLines")}</span><span className="ag-spacer" />
      <div role="group" aria-label={t("studio.diffLayout")}>{(["unified", "split"] as const).map((option) => <button type="button" className="ag-chip" key={option} aria-pressed={layout === option} onClick={() => setLayout(option)}>{t(`studio.${option}`)}</button>)}</div>
    </div>
    <div className={`diff-grid ${layout === "unified" || before === null ? "diff-grid--single" : ""}`}>
      {sections.map((section) => <section key={section.id} className={`ag-diff-hunk ${decisions[section.id] ? `is-${decisions[section.id]}` : ""} ${focused === section.id ? "is-focused" : ""}`} onFocus={() => { if (section.changed) setFocused(section.id); }}>
        {section.changed && onDecision && <header className="ag-hunk-bar"><code>@@ {section.ops.find((op) => op.oldNo)?.oldNo ?? 0} → {section.ops.find((op) => op.newNo)?.newNo ?? 0} @@</code><span className="ag-spacer" />{decisions[section.id] && <span className="decision">{t(decisions[section.id] === "accepted" ? "stage.accepted" : "stage.rejected")}</span>}<button type="button" className="ag-chip" onClick={() => { setFocused(section.id); onDecision(section.id, "accepted"); }}>{t("stage.accept")} <kbd>⌘/Ctrl Y</kbd></button><button type="button" className="ag-chip" onClick={() => { setFocused(section.id); onDecision(section.id, "rejected"); }}>{t("stage.reject")} <kbd>⌘/Ctrl N</kbd></button></header>}
        {layout === "unified" || before === null
          ? section.ops.map((op, index) => <div className="diff-row" key={index}><span className="diff-no">{op.newNo ?? op.oldNo}</span><code className={`diff-code ${op.type === "add" ? "diff-code--add" : op.type === "del" ? "diff-code--del" : ""}`}><span className="ag-diff-sign">{op.type === "add" ? "+" : op.type === "del" ? "−" : " "}</span><Syntax text={op.text} filename={filename} /></code></div>)
          : splitRows(section.ops).map((row, index) => <div className="diff-row diff-row--split" key={index}><Cell op={row.left} side="left" filename={filename} /><Cell op={row.right} side="right" filename={filename} /></div>)}
      </section>)}
    </div>
  </div>;
}
