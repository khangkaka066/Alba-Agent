"use client";

import { useState } from "react";
import { useLocale } from "@/components/locale-provider";
import { PromptBox } from "./prompt-box";
import { SlashMenu } from "./composer";
import { useWorkspace } from "./workspace-context";

const STARTERS = ["home.starter.museum", "home.starter.excel", "home.starter.webapp"];

/** State A: nothing is running, so the screen is one centred question and a few ways to start. */
export function StudioHome({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { t } = useLocale();
  const workspace = useWorkspace();
  const [text, setText] = useState("");
  const [slash, setSlash] = useState(false);
  const { token } = workspace;

  const submit = (value: string) => {
    const prompt = value.trim();
    if (!prompt || workspace.uploading || workspace.uploads.some((item) => item.status === "error") || !token) return;
    setText("");
    workspace.sendTask(prompt, workspace.rigor);
  };

  return <div className="studio-home">
    <div className="studio-home__inner">
      <h1>{t("home.title")}</h1>
      <form className="ag-composer" onSubmit={(event) => { event.preventDefault(); submit(text); }}>
        {slash && <SlashMenu onClose={() => { setSlash(false); if (text.trim() === "/") setText(""); }} />}
        <PromptBox value={text} onChange={setText} onSubmit={() => submit(text)} onSlash={() => setSlash(true)} onOpenSettings={onOpenSettings} autoFocus rows={1}
          label={t("home.promptLabel")} placeholder={t(token ? "prompt.placeholder" : "home.starting")} busy={workspace.busy} canSend={Boolean(text.trim() && token)} />
      </form>
      <div className="starter-chips" aria-label={t("home.hints")}>{STARTERS.map((key) => <button key={key} className="chip chip--starter" disabled={workspace.busy || !token} onClick={() => submit(t(key))}>{t(key)}</button>)}</div>
    </div>
  </div>;
}
