"use client";

import { useEffect, useRef, useState } from "react";
import { NexusOctopusLogo } from "@/components/brand/nexus-octopus-logo";
import { apiRequest, readError } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";

/** Floating mini-bar summoned by the desktop global shortcut: one line in, the team starts in the background. */
export function QuickBar() {
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
    input.current?.focus();
    const refocus = () => { setState("idle"); setMessage(""); setText(""); input.current?.focus(); };
    window.addEventListener("focus", refocus);
    return () => window.removeEventListener("focus", refocus);
  }, []);

  const send = async () => {
    const prompt = text.trim();
    if (!prompt || state === "sending") return;
    const token = window.localStorage.getItem("nexus_access_token") ?? "";
    if (!token) { setState("error"); setMessage("Open Alba Agent and connect a workspace first."); return; }
    setState("sending"); setMessage("");
    try {
      await apiRequest("/api/v1/architect/generate-workflow", token, { method: "POST", body: JSON.stringify({ user_requirement_prompt: prompt, auto_run: true }) });
      setState("sent"); setMessage("Team started. You will be notified when it needs you or finishes.");
      getDesktop()?.notify("Team started", prompt.slice(0, 120));
      window.setTimeout(() => getDesktop()?.hideQuickBar(), 900);
    } catch (error) { setState("error"); setMessage(readError(error)); }
  };

  return <main className="quickbar">
    <NexusOctopusLogo size={28} />
    <input ref={input} aria-label="Quick task for your agent team" value={text} disabled={state === "sending"} placeholder="Delegate a task to your agent team…"
      onChange={(event) => setText(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter" && !event.nativeEvent.isComposing) void send();
        if (event.key === "Escape") getDesktop()?.hideQuickBar();
      }} />
    <span className={`quickbar-status quickbar-status--${state}`} role="status">{state === "sending" ? "Starting…" : message || "Enter to run · Esc to close"}</span>
  </main>;
}
