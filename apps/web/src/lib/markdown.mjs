/** Small, text-only Markdown parser. HTML is always rendered as text by React. */
export function safeLink(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return ["https:", "http:", "mailto:"].includes(url.protocol) ? url.href : null;
  } catch { return value.startsWith("#") ? value : null; }
}

export function markdownBlocks(text) {
  const lines = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  const tableRow = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
  const startsBlock = (line, next) => /^\s*(```|~~~|#{1,6}\s|>\s?|[-*+]\s|\d+\.\s)/.test(line) || /^(?:\s*[-*_]){3,}\s*$/.test(line) || (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next ?? ""));
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    const fence = line.match(/^\s*(```|~~~)([^\s]*)\s*$/);
    if (fence) {
      const content = []; i += 1;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) content.push(lines[i++]);
      if (i < lines.length) i += 1;
      blocks.push({ kind: "code", language: fence[2], text: content.join("\n") }); continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) { blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] }); i += 1; continue; }
    if (/^(?:\s*[-*_]){3,}\s*$/.test(line)) { blocks.push({ kind: "rule" }); i += 1; continue; }
    if (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1] ?? "")) {
      const headers = tableRow(line), rows = []; i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) rows.push(tableRow(lines[i++]));
      blocks.push({ kind: "table", headers, rows }); continue;
    }
    if (/^\s*>/.test(line)) {
      const content = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) content.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push({ kind: "quote", text: content.join("\n") }); continue;
    }
    const list = line.match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/);
    if (list) {
      const items = [], ordered = !!list[2];
      while (i < lines.length) {
        const item = lines[i].match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/);
        if (!item || !!item[2] !== ordered) break;
        items.push(item[3]); i += 1;
      }
      blocks.push({ kind: "list", ordered, start: ordered ? Number(list[2]) : 1, items }); continue;
    }
    const content = [line]; i += 1;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1])) content.push(lines[i++]);
    blocks.push({ kind: "paragraph", text: content.join("\n") });
  }
  return blocks;
}
