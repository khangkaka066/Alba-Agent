"use client";

import { useEffect, useRef, useState } from "react";
import { apiRequest, readError } from "@/lib/api";
import { readSse } from "@/lib/sse";
import { useWorkspace } from "./workspace-context";

export type ComputerSession = { computer_id: string; cwd: string; active_process_id: string | null; ports: number[]; sequence: number;
  processes: Array<{ id: string; pid: number; command: string; running: boolean; background: boolean; ports: number[]; exit_code: number | null }>;
  snapshots: Array<{ id: string; created_at: number; size_bytes: number }>;
  resources: { cpu_percent: string | number | null; memory?: string; memory_bytes?: number | null; scope?: string };
};
export type ComputerLine = { sequence: number; stream: string; text: string };

export function useComputer(enabled: boolean, autoPreview = true) {
  const { token, runId } = useWorkspace();
  const [computerId, setComputerId] = useState<string | null>(null);
  const [session, setSession] = useState<ComputerSession | null>(null);
  const [lines, setLines] = useState<ComputerLine[]>([]);
  const [creating, setCreating] = useState(false);
  const createPending = useRef(false);
  const [error, setError] = useState("");
  const stdinEpoch = useRef(0);
  const stdinSocket = useRef<WebSocket | null>(null);
  const stdinReady = useRef(false);
  const pendingInput = useRef<{ resolve: () => void; reject: (reason: Error) => void; timer: number } | null>(null);
  const stdinQueue = useRef<Promise<void>>(Promise.resolve());
  useEffect(() => {
    stdinEpoch.current += 1;
    if (!enabled || !computerId || !token) return;
    const url = new URL(`/api/v1/sandboxes/${computerId}/terminal/input`, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    stdinSocket.current = socket; stdinReady.current = false;
    const disconnected = () => {
      stdinReady.current = false;
      const pending = pendingInput.current; pendingInput.current = null;
      if (pending) { window.clearTimeout(pending.timer); pending.reject(new Error("Terminal input connection closed before acknowledgement")); }
    };
    socket.onopen = () => socket.send(JSON.stringify({ token }));
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(String(event.data)) as { ready?: boolean; ok?: boolean };
        if (message.ready) { stdinReady.current = true; return; }
        if (message.ok && pendingInput.current) { const pending = pendingInput.current; pendingInput.current = null; window.clearTimeout(pending.timer); pending.resolve(); }
      } catch { socket.close(); }
    };
    socket.onerror = disconnected; socket.onclose = disconnected;
    return () => { stdinEpoch.current += 1; disconnected(); socket.onopen = null; socket.onmessage = null; socket.onerror = null; socket.onclose = null; socket.close(); if (stdinSocket.current === socket) stdinSocket.current = null; };
  }, [enabled, computerId, token]);
  const sendInput = (data: string, processId: string | null | undefined): Promise<void> => {
    const epoch = stdinEpoch.current;
    const task = stdinQueue.current.catch(() => undefined).then(async () => {
      if (epoch !== stdinEpoch.current) throw new Error("Computer changed before input was sent");
      const socket = stdinSocket.current;
      const body = { data, process_id: processId };
      if (!socket || !stdinReady.current || socket.readyState !== WebSocket.OPEN) {
        await apiRequest(`/api/v1/sandboxes/${computerId}/terminal/input`, token, { method: "POST", body: JSON.stringify(body) });
        return;
      }
      await new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(() => { socket.close(); reject(new Error("Input acknowledgement timed out; check the process before sending again")); }, 5000);
        pendingInput.current = { resolve, reject, timer };
        socket.send(JSON.stringify(body));
      });
    });
    stdinQueue.current = task;
    return task;
  };
  const cursor = useRef(0);
  const previewed = useRef(new Set<number>());
  useEffect(() => { setComputerId(null); setSession(null); setLines([]); setError(""); cursor.current = 0; previewed.current.clear(); }, [runId, token]);
  useEffect(() => {
    if (!enabled || !token || !runId) return;
    let stopped = false;
    const discover = async () => {
      try {
        const rows = await apiRequest<Array<{ id: string; run_id: string | null; status: string }>>("/api/v1/sandboxes", token);
        const match = rows.find((row) => row.run_id === runId && row.status === "running");
        if (!stopped) setComputerId(match?.id ?? null);
      } catch (reason) { if (!stopped) setError(readError(reason)); }
    };
    void discover();
    const timer = window.setInterval(() => void discover(), 3000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [enabled, token, runId]);
  useEffect(() => {
    if (!enabled || !computerId || !token) return;
    const controller = new AbortController();
    let reconnect: number | undefined;
    const connect = async () => {
      try {
        const response = await fetch(`/api/v1/sandboxes/${computerId}/terminal/events?after=${cursor.current}`, { headers: { authorization: `Bearer ${token}` }, signal: controller.signal, cache: "no-store" });
        await readSse(response, (name, data) => {
          if (name === "session") {
            const next = JSON.parse(data) as ComputerSession;
            setSession(next);
            for (const port of next.ports) if (autoPreview && !previewed.current.has(port)) {
              const processId = next.processes.find((job) => job.running && job.ports.includes(port))?.id;
              window.dispatchEvent(new CustomEvent("nexus:sandbox-preview", { detail: { computerId, port, processId } }));
            }
            previewed.current = new Set(next.ports);
            return;
          }
          const event = JSON.parse(data) as { type: string; sequence: number; stream?: string; text?: string; port?: number; error_digest?: { root_cause_line: string } };
          if (event.sequence <= cursor.current) return;
          cursor.current = event.sequence;
          if (event.type === "TERMINAL_OUTPUT") setLines((current) => [...current, { sequence: event.sequence, stream: event.stream ?? "stdout", text: event.text ?? "" }].slice(-1000));
          if (event.type === "PROCESS_EXITED" && event.error_digest) setLines((current) => [...current, { sequence: event.sequence, stream: "digest", text: event.error_digest?.root_cause_line ?? "" }].slice(-1000));
        }, controller.signal);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setError(readError(reason));
        if (/\((404|410)\)/.test(readError(reason))) { setComputerId(null); return; } // the computer is gone; discovery will find a new one
      }
      if (!controller.signal.aborted) reconnect = window.setTimeout(() => void connect(), 1500);
    };
    void connect();
    return () => { controller.abort(); if (reconnect) window.clearTimeout(reconnect); };
  }, [enabled, computerId, token, autoPreview]);
  const create = async () => {
    if (!runId || createPending.current) return;
    createPending.current = true; setCreating(true);
    try {
      const row = await apiRequest<{ id: string }>("/api/v1/sandboxes", token, { method: "POST", body: JSON.stringify({ run_id: runId, visibility: "private" }) });
      setComputerId(row.id); setError("");
    } catch (reason) { setError(readError(reason)); }
    finally { createPending.current = false; setCreating(false); }
  };
  return { computerId, session, lines, error, setError, create, creating, sendInput, clear: () => setLines([]) };
}
