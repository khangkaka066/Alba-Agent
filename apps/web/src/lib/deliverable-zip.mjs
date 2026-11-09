/** Original ZIP writer using the store method. Media is already compressed; no dependency is needed. */
export function deliverableZip(files) {
  const encoder = new TextEncoder();
  const parts = [], directory = [];
  let offset = 0, directorySize = 0;
  const names = new Set();
  if (files.length > 65535) throw new Error("Too many deliverables for one archive");
  for (const file of files) {
    const path = file.name.replaceAll("\\", "/");
    if (!path || path.startsWith("/") || /^[a-z]:/i.test(path) || path.split("/").some((part) => !part || part === ".." || part === ".") || /[\x00-\x1f]/.test(path) || names.has(path)) throw new Error("Unsafe or duplicate deliverable path");
    names.add(path);
    const name = encoder.encode(path), bytes = file.data;
    if (name.length > 65535 || bytes.length > 0xffffffff || offset + bytes.length > 0xffffffff) throw new Error("Archive exceeds ZIP size limits");
    let crc = 0xffffffff;
    for (const byte of bytes) { crc ^= byte; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0); }
    crc = (crc ^ 0xffffffff) >>> 0;
    const local = new Uint8Array(30 + name.length), lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true); lv.setUint16(4, 20, true); lv.setUint16(6, 0x800, true);
    lv.setUint16(12, 33, true); lv.setUint32(14, crc, true); lv.setUint32(18, bytes.length, true); lv.setUint32(22, bytes.length, true); lv.setUint16(26, name.length, true); local.set(name, 30);
    const entry = new Uint8Array(46 + name.length), ev = new DataView(entry.buffer);
    ev.setUint32(0, 0x02014b50, true); ev.setUint16(4, 20, true); ev.setUint16(6, 20, true); ev.setUint16(8, 0x800, true);
    ev.setUint16(14, 33, true); ev.setUint32(16, crc, true); ev.setUint32(20, bytes.length, true); ev.setUint32(24, bytes.length, true); ev.setUint16(28, name.length, true); ev.setUint32(42, offset, true); entry.set(name, 46);
    parts.push(local, bytes); directory.push(entry); offset += local.length + bytes.length; directorySize += entry.length;
  }
  const end = new Uint8Array(22), view = new DataView(end.buffer);
  view.setUint32(0, 0x06054b50, true); view.setUint16(8, files.length, true); view.setUint16(10, files.length, true); view.setUint32(12, directorySize, true); view.setUint32(16, offset, true);
  return new Blob([...parts, ...directory, end], { type: "application/zip" });
}
