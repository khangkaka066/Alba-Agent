"use client";

import { Fragment, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { markdownBlocks, safeLink } from "@/lib/markdown.mjs";

function Inline({ text }: { text: string }) {
  return <>{text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={index}>{part.slice(1, -1)}</em>;
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) { const href = safeLink(link[2]); return href ? <a key={index} href={href} target={href.startsWith("#") ? undefined : "_blank"} rel="noopener noreferrer">{link[1]}</a> : <Fragment key={index}>{link[1]}</Fragment>; }
    return <Fragment key={index}>{part}</Fragment>;
  })}</>;
}

function CodeBlock({ text, language }: { text: string; language: string }) {
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);
  return <div className="nx-code"><header><span>{language || t("interface.code")}</span><button type="button" onClick={() => void navigator.clipboard.writeText(text).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1800); })}><Icon name={copied ? "check" : "copy"} size={13} />{t(copied ? "interface.copied" : "common.copy")}</button></header><pre><code>{text}</code></pre></div>;
}

export function MessageContent({ text }: { text: string }) {
  return <div className="nx-markdown">{markdownBlocks(text).map((block, index) => {
    switch (block.kind) {
      case "code": return <CodeBlock key={index} text={block.text} language={block.language} />;
      case "heading": return block.level <= 2 ? <h2 key={index}><Inline text={block.text} /></h2> : <h3 key={index}><Inline text={block.text} /></h3>;
      case "rule": return <hr key={index} />;
      case "table": return <div key={index} className="nx-markdown-table"><table><thead><tr>{block.headers.map((cell, at) => <th key={at}><Inline text={cell} /></th>)}</tr></thead><tbody>{block.rows.map((row, at) => <tr key={at}>{block.headers.map((_, column) => <td key={column}><Inline text={row[column] ?? ""} /></td>)}</tr>)}</tbody></table></div>;
      case "quote": return <blockquote key={index}><Inline text={block.text} /></blockquote>;
      case "list": { const items = block.items.map((item, at) => <li key={at}><Inline text={item} /></li>); return block.ordered ? <ol key={index} start={block.start}>{items}</ol> : <ul key={index}>{items}</ul>; }
      default: return <p key={index}><Inline text={block.text} /></p>;
    }
  })}</div>;
}
