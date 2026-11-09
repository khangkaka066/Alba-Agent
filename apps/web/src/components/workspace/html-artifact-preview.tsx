"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { Icon } from "@/components/shell/icons";
import { readError } from "@/lib/api";
import { useWorkspace, type Artifact } from "./workspace-context";

export function isHtmlArtifact(artifact: Artifact): boolean {
  return /\.html?$/i.test(artifact.filename) || artifact.mime_type.split(";", 1)[0] === "text/html";
}

/** Opaque iframe origin keeps generated scripts away from the app's session and DOM. */
export function HtmlArtifactPreview({ artifact, toolbar = true }: { artifact: Artifact; toolbar?: boolean }) {
  const { t } = useLocale();
  const { fetchArtifact, runId } = useWorkspace();
  const [html, setHtml] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [revision, setRevision] = useState(0);
  const source = useRef(artifact); source.current = artifact;
  useEffect(() => {
    let stopped = false;
    setHtml(null); setProblem("");
    void fetchArtifact(source.current, "text").then((text) => { if (!stopped && typeof text === "string") setHtml(text); }).catch((error) => { if (!stopped) setProblem(readError(error)); });
    return () => { stopped = true; };
  }, [artifact.filename, artifact.download_url, artifact.size_bytes, fetchArtifact, runId, revision]);
  return <div className="ag-html-preview">
    {toolbar && <header><Icon name="globe" size={15} /><span>{artifact.filename}</span><button type="button" className="ag-iconbtn" aria-label={t("browser.reload")} onClick={() => setRevision((value) => value + 1)}><Icon name="refresh" size={14} /></button></header>}
    {problem ? <p role="alert" className="ag-browser__problem">{problem}</p> : html === null ? <p className="ag-empty">{t("stage.loadingFile", { name: artifact.filename })}</p>
      : <iframe key={`${runId}/${artifact.filename}/${revision}`} className="ag-html-preview__frame" title={t("result.previewTitle", { name: artifact.filename })} srcDoc={html} sandbox="allow-scripts" referrerPolicy="no-referrer" />}
  </div>;
}
