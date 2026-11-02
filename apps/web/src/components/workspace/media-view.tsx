"use client";

import { useEffect, useState } from "react";
import type { ArtifactKind } from "@/lib/workspace.mjs";
import { useLocale } from "@/components/locale-provider";
import { useWorkspace, type Artifact } from "./workspace-context";

/** Fetches a binary deliverable with the session token and exposes it as an object URL. */
export function MediaView({ artifact, kind }: { artifact: Artifact; kind: ArtifactKind }) {
  const { t } = useLocale();
  const { fetchArtifact } = useWorkspace();
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = ""; let stopped = false;
    setUrl(""); setFailed(false);
    void fetchArtifact(artifact, "blob").then((blob) => {
      if (stopped) return;
      if (!(blob instanceof Blob)) { setFailed(true); return; }
      current = URL.createObjectURL(blob); setUrl(current);
    }).catch(() => { if (!stopped) setFailed(true); });
    return () => { stopped = true; if (current) URL.revokeObjectURL(current); };
  }, [artifact, fetchArtifact]);
  if (failed) return <p className="stage-empty">{t("stage.loadFailed")}</p>;
  if (!url) return <p className="stage-empty">{t("stage.loadingFile", { name: artifact.filename })}</p>;
  if (kind === "video") return <video className="media-player" src={url} controls aria-label={artifact.filename} />;
  if (kind === "audio") return <audio className="media-audio" src={url} controls aria-label={artifact.filename} />;
  if (kind === "pdf") return <iframe className="media-frame" src={url} title={artifact.filename} />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="media-image" src={url} alt={artifact.filename} />;
}
