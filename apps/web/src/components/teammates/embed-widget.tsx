"use client";

import { useEffect, useState } from "react";
import { NexusLogo } from "@/components/brand/nexus-agent-logo";

type RuntimeEvent = { type: string; payload: Record<string, unknown> };

export function EmbedWidget({ workflowId }: { workflowId: string }) {
  const [token, setToken] = useState(""); const [request, setRequest] = useState(""); const [answer, setAnswer] = useState(""); const [status, setStatus] = useState("Ready"); const [busy, setBusy] = useState(false);
  useEffect(() => setToken(window.localStorage.getItem("nexus_access_token") ?? ""), []);
  const run = async () => {
    if (!token || !request.trim()) { setStatus("Sign in to the workspace in this browser before running."); return; }
    setBusy(true); setAnswer(""); setStatus("Starting workflow…");
    try {
      const response = await fetch(`/api/v1/workflows/${workflowId}/runs`, { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ input_data: { request } }) });
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json() as { run_id: string };
      setStatus(`Listening to run ${result.run_id.slice(0, 8)}…`);
      const stream = await fetch(`/api/v1/runs/${result.run_id}/stream`, { headers: { authorization: `Bearer ${token}`, accept: "text/event-stream" } });
      if (!stream.ok || !stream.body) throw new Error(`Run stream unavailable (${stream.status})`);
      const reader = stream.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
          const data = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
          if (data) {
            const event = JSON.parse(data) as RuntimeEvent;
            if (event.type === "RUN_COMPLETED") {
              setStatus("Completed");
              const finalResponse = await fetch(`/api/v1/runs/${result.run_id}`, { headers: { authorization: `Bearer ${token}` } });
              if (finalResponse.ok) { const finalRun = await finalResponse.json() as { node_outputs?: Record<string, unknown> }; setAnswer(JSON.stringify(finalRun.node_outputs ?? event.payload, null, 2)); }
              await reader.cancel(); return;
            }
            if (event.type === "RUN_FAILED") { setStatus("Run failed"); setAnswer(String(event.payload.error_type ?? "The workflow could not complete.")); await reader.cancel(); return; }
            if (event.type === "FLOW_STATE_CHANGED") setStatus(`Working · ${String(event.payload.node_id ?? "workflow")}`);
            if (event.type === "APPROVAL_REQUIRED") setStatus("Waiting for workspace approval");
          }
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (error) { setStatus(error instanceof Error ? error.message : "Workflow request failed"); }
    finally { setBusy(false); }
  };
  return <main className="embed-shell"><div className="embed-brand"><NexusLogo size={27} /> <span>Alba Agent</span></div><section className="embed-card"><span className="eyebrow">WORKSPACE WORKFLOW</span><h1>How can we help?</h1><p>Your request will run inside the workspace connected in this browser.</p><textarea rows={4} value={request} onChange={(event) => setRequest(event.target.value)} placeholder="Describe what you need…" /><button className="button button-primary" disabled={busy || !request.trim()} onClick={() => void run()}>{busy ? "Running…" : "Send request ↑"}</button><div className="embed-status"><span className={status === "Completed" ? "live-indicator" : ""} />{status}</div>{answer && <pre className="embed-answer">{answer}</pre>}</section></main>;
}
