"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { apiRequest } from "@/lib/api";

type Artifact = { filename: string; mime_type: string; size_bytes: number; download_url: string; preview_url: string; created_by_node: string | null };

export function RunArtifactGallery({ runId, token }: { runId: string; token: string }) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    let stopped = false;
    const urls = new Map<string, string>();
    const refresh = async () => {
      try {
        const rows = await apiRequest<Artifact[]>(`/api/v1/runs/${runId}/artifacts`, token);
        if (stopped) return;
        setArtifacts(rows);
        for (const item of rows) {
          if (urls.has(item.filename) || item.size_bytes > 50_000_000 || !/^(image|video|audio)\//.test(item.mime_type)) continue;
          const response = await fetch(item.preview_url, { headers: { authorization: `Bearer ${token}` } });
          if (!response.ok || stopped) continue;
          const url = URL.createObjectURL(await response.blob());
          urls.set(item.filename, url);
          setPreviewUrls(Object.fromEntries(urls));
        }
      } catch { if (!stopped) setError("Files are temporarily unavailable."); }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { stopped = true; window.clearInterval(timer); urls.forEach((url) => URL.revokeObjectURL(url)); };
  }, [runId, token]);

  const download = async (item: Artifact) => {
    const response = await fetch(item.download_url, { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) { setError(`Download failed (${response.status}).`); return; }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a"); link.href = url; link.download = item.filename; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return <section className="run-artifacts"><h3>Generated Deliverables &amp; Files</h3>{error && <p role="alert">{error}</p>}{artifacts.length ? <div className="run-artifact-grid">{artifacts.map((item) => <article key={item.filename} className="run-artifact-card">{item.mime_type.startsWith("video/") && previewUrls[item.filename] && <video controls src={previewUrls[item.filename]} />}{item.mime_type.startsWith("audio/") && previewUrls[item.filename] && <audio controls src={previewUrls[item.filename]} />}{item.mime_type.startsWith("image/") && previewUrls[item.filename] && <Image src={previewUrls[item.filename]} alt={item.filename} width={320} height={180} unoptimized /> }<strong>{item.filename}</strong><small>{item.mime_type} · {(item.size_bytes / 1024).toFixed(1)} KB</small><button className="button button-small" onClick={() => void download(item)}>Download File</button></article>)}</div> : <p>Files will appear as agents create them.</p>}</section>;
}
