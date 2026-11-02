"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { classifyArtifact, isFinished, liveActivity, stepLabel } from "@/lib/workspace.mjs";
import { DiffView } from "./diff-view";
import { MediaView } from "./media-view";
import { useWorkspace } from "./workspace-context";

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
  return <div className="file-stage">
    <header className="file-stage-head">
      <strong title={artifact.filename}>{artifact.filename}</strong>
      <span className="file-stage-meta">{(artifact.size_bytes / 1024).toFixed(1)} KB{workspace.statuses[artifact.filename] ? ` · ${workspace.statuses[artifact.filename] === "added" ? t("stage.new") : t("stage.edited")}` : ""}</span>
      <span className="file-stage-spacer" />
      {decision && <span className={`decision decision--${decision}`}>{decision === "accepted" ? t("stage.accepted") : t("stage.rejected")}</span>}
      <button className="button button-quiet" onClick={() => void workspace.download(artifact)}>{t("stage.download")}</button>
      <button className="button button-quiet" onClick={() => workspace.reject(artifact)} disabled={decision === "rejected"}>{t("stage.reject")}</button>
      <button className="button button-primary" onClick={() => void workspace.accept(artifact)} disabled={decision === "accepted"}>{workspace.folder ? t("stage.acceptInto", { name: workspace.folder.name }) : t("stage.accept")}</button>
    </header>
    <div className="file-stage-body">
      {kind.text
        ? content ? <DiffView before={content.before} after={content.after} filename={artifact.filename} /> : <p className="stage-empty">{t("stage.loadingFile", { name: artifact.filename })}</p>
        : kind.kind === "other" ? <p className="stage-empty">{t("stage.noPreview")}</p>
        : <MediaView artifact={artifact} kind={kind.kind} />}
    </div>
  </div>;
}

/** Right stage while a task exists: the file the team produced, or a calm status until the first file lands. */
export function Workbench() {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const { run, team, artifacts, selected } = workspace;
  if (artifacts.length && selected) return <div className="workbench"><FileStage /></div>;
  const failed = run.status === "failed";
  return <div className="workbench"><div className="stage-empty stage-empty--hero stage-waiting">
    <h2>{failed ? t("stage.notFinished") : isFinished(run.status) ? t("stage.noFiles") : t("chat.teamWorking")}</h2>
    <p>{failed ? run.error || t("stage.errorFallback") : liveActivity(run, t)}</p>
    {!isFinished(run.status) && team.steps > 0 && <p className="stage-waiting__step">{stepLabel(run, team.steps)}</p>}
    {!isFinished(run.status) && <span className="stage-waiting__bar" aria-hidden="true"><i /></span>}
  </div></div>;
}
