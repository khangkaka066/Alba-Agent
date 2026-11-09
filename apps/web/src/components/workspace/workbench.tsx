"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { classifyArtifact } from "@/lib/workspace.mjs";
import { DiffView } from "./diff-view";
import { MediaView } from "./media-view";
import { useWorkspace } from "./workspace-context";
import { HtmlArtifactPreview, isHtmlArtifact } from "./html-artifact-preview";
import { MessageContent } from "./message-content";

function FileStage() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const artifact = workspace.artifacts.find((item) => item.filename === workspace.selected) ?? null;
  const [content, setContent] = useState<{ before: string | null; after: string } | null>(null);
  const kind = artifact ? classifyArtifact(artifact.filename, artifact.mime_type) : null;
  const { fetchArtifact, beforeText } = workspace;
  useEffect(() => {
    setContent(null);
    if (!artifact || !kind?.text) return;
    let stopped = false;
    void (async () => {
      const after = await fetchArtifact(artifact, "text");
      const before = await beforeText(artifact.filename).catch(() => null);
      if (!stopped && typeof after === "string") setContent({ before, after });
    })();
    return () => { stopped = true; };
  }, [artifact, kind?.text, fetchArtifact, beforeText]);

  if (!artifact || !kind) return null;
  const decision = workspace.decisions[artifact.filename];
  const markdown = /\.(md|markdown)$/i.test(artifact.filename);
  return <div className="file-stage">
    <header className="file-stage-head">
      <strong title={artifact.filename}>{artifact.filename}</strong>
      <span className="file-stage-meta">{(artifact.size_bytes / 1024).toFixed(1)} KB{workspace.statuses[artifact.filename] ? ` · ${workspace.statuses[artifact.filename] === "added" ? t("stage.new") : t("stage.edited")}` : ""}</span>
      <span className="file-stage-spacer" />
      {(isHtmlArtifact(artifact) || markdown) && <><button type="button" className="button button-quiet" aria-pressed={workspace.artifactView === "preview"} onClick={() => workspace.setArtifactView("preview")}>{t("result.preview")}</button><button type="button" className="button button-quiet" aria-pressed={workspace.artifactView === "diff"} onClick={() => workspace.setArtifactView("diff")}>{t("result.diff")}</button></>}
      {decision && <span className={`decision decision--${decision}`}>{decision === "accepted" ? t("stage.accepted") : t("stage.rejected")}</span>}
      <button className="button button-quiet" onClick={() => void workspace.download(artifact)}>{t("stage.download")}</button>
      <button className="button button-quiet" onClick={() => workspace.reject(artifact)} disabled={decision === "rejected"}>{t("stage.reject")}</button>
      <button className="button button-primary" onClick={() => void workspace.accept(artifact)} disabled={decision === "accepted"}>{workspace.folder ? t("stage.acceptInto", { name: workspace.folder.name }) : t("stage.accept")}</button>
    </header>
    <div className="file-stage-body">
      {isHtmlArtifact(artifact) && workspace.artifactView === "preview" ? <HtmlArtifactPreview artifact={artifact} toolbar={false} /> : markdown && workspace.artifactView === "preview" && content ? <div className="nx-document-preview"><MessageContent text={content.after} /></div> : kind.text
        ? content ? <DiffView key={`${workspace.runId}/${artifact.filename}`} before={content.before} after={content.after} filename={artifact.filename} decisions={workspace.reviews[artifact.filename]?.after === content.after ? workspace.reviews[artifact.filename].hunks : {}} onDecision={(id, decision) => workspace.reviewHunk(artifact.filename, content.before, content.after, id, decision)} /> : <p className="stage-empty">{t("stage.loadingFile", { name: artifact.filename })}</p>
        : kind.kind === "other" ? <p className="stage-empty">{t("stage.noPreview")}</p>
        : <MediaView artifact={artifact} kind={kind.kind} />}
    </div>
  </div>;
}

/** The file pane shows deliverables; execution activity stays in the conversation. */
export function Workbench() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { artifacts, selected } = workspace;
  if (artifacts.length && selected) return <div className="workbench"><FileStage /></div>;
  return <div className="workbench"><p className="stage-empty">{t("dock.noModified")}</p></div>;
}
