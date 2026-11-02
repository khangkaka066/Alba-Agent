"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, readError } from "@/lib/api";
import { ApprovalCard, type PendingApproval } from "./approval-card";

const THINKING = "Your teammate is thinking…";

type Scope = { tenant_id: string; workspace_id: string };
type Bot = { id: string; name: string; description: string; model: string; memory_namespace: string; tenant_id: string; workspace_id: string; billing_mode?: string };
type Routine = { id: string; bot_id: string; name: string; instruction_markdown: string; cron_expression: string; timezone: string; enabled: boolean; tenant_id: string; workspace_id: string; interval_seconds?: number | null };
type Message = { role: "user" | "assistant" | "system"; content: string };

export function TeammateWorkspace({ token, scope, incomingApprovals, onApprovalResolved, onConnect }: { token: string; scope: Scope; incomingApprovals: PendingApproval[]; onApprovalResolved: (id: string) => void; onConnect: () => void }) {
  const [bots, setBots] = useState<Bot[]>([]);
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [selectedBot, setSelectedBot] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [threadId, setThreadId] = useState("");
  const [tab, setTab] = useState<"chat" | "routines">("chat");
  const [routine, setRoutine] = useState({ name: "Weekly customer pulse", instruction_markdown: "Review recent customer feedback.\n\nSummarize recurring themes, urgent issues, and one suggested follow-up.", cron_expression: "0 9 * * 1", timezone: "UTC" });
  const [schedulePreset, setSchedulePreset] = useState("weekly");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiceToken, setVoiceToken] = useState("");
  const [voiceState, setVoiceState] = useState("off");
  const voiceSocket = useRef<WebSocket | null>(null);
  const voiceStream = useRef<MediaStream | null>(null);
  const voiceRecorder = useRef<MediaRecorder | null>(null);
  const voiceAudioChunks = useRef<Uint8Array[]>([]);
  const activeBot = bots.find((bot) => bot.id === selectedBot);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [botList, routineList] = await Promise.all([apiRequest<Bot[]>("/api/v1/bots", token), apiRequest<Routine[]>("/api/v1/routines", token)]);
      setBots(botList); setRoutines(routineList); setSelectedBot((current) => current || botList[0]?.id || "");
    } catch (error) { setStatus(readError(error)); }
  }, [token]);
  useEffect(() => { setStatus(""); void load(); }, [load]);
  useEffect(() => {
    const newChat = () => { setThreadId(""); setMessages([]); setText(""); setTab("chat"); };
    window.addEventListener("nexus:new-chat", newChat);
    return () => window.removeEventListener("nexus:new-chat", newChat);
  }, []);

  const send = async (botId = selectedBot, content = text.trim()) => {
    if (!content || !botId || !token) return;
    const currentThread = threadId || crypto.randomUUID();
    setText(""); setThreadId(currentThread); setMessages((current) => [...current, { role: "user", content }, { role: "system", content: THINKING }]);
    try {
      await apiRequest(`/api/v1/bots/${botId}/turns`, token, { method: "POST", body: JSON.stringify({ content, thread_id: currentThread }) });
      let attempts = 0;
      const poll = async (): Promise<void> => {
        const history = await apiRequest<Message[]>(`/api/v1/bots/${botId}/threads/${currentThread}`, token);
        if (history.length && history[history.length - 1].role !== "user") { setMessages(history); return; }
        attempts += 1;
        if (attempts < 90) window.setTimeout(() => void poll(), 2000);
        else setMessages((current) => [...current.filter((message) => message.role !== "system"), { role: "system", content: "Your teammate did not respond in time. Check Settings → Providers for a model key, then try again." }]);
      };
      window.setTimeout(() => void poll().catch((error: unknown) => setStatus(readError(error))), 1200);
    } catch (error) { setStatus(readError(error)); setMessages((current) => current.filter((message) => message.role !== "system")); }
  };

  const createBot = async () => {
    if (!token) { onConnect(); return; }
    setBusy(true);
    const id = crypto.randomUUID();
    const spec = { id, ...scope, name: "Studio teammate", description: "A persistent assistant for this workspace", model: "openai/gpt-4.1-mini", memory_namespace: `bot:${id}`, billing_mode: "platform" };
    try { const created = await apiRequest<Bot>("/api/v1/bots", token, { method: "POST", body: JSON.stringify(spec) }); setBots((current) => [...current, created]); setSelectedBot(created.id); setStatus("Teammate created."); return created; }
    catch (error) { setStatus(readError(error)); }
    finally { setBusy(false); }
  };

  const createRoutine = async () => {
    if (!token || !activeBot) { setStatus("Choose a teammate and connect to the API before saving a routine."); return; }
    setBusy(true);
    try {
      const created = await apiRequest<Routine>("/api/v1/routines", token, { method: "POST", body: JSON.stringify({ id: crypto.randomUUID(), ...scope, bot_id: activeBot.id, ...routine, enabled: true }) });
      setRoutines((current) => [created, ...current]); setStatus("Routine scheduled.");
    } catch (error) { setStatus(readError(error)); }
    finally { setBusy(false); }
  };

  const runRoutine = async (id: string) => {
    try { const result = await apiRequest<{ run_id: string }>(`/api/v1/routines/${id}/runs`, token, { method: "POST" }); setStatus(`Routine queued · ${result.run_id.slice(0, 8)}`); }
    catch (error) { setStatus(readError(error)); }
  };

  const startVoice = async () => {
    if (!activeBot) return;
    try {
      const result = await apiRequest<{ token: string; expires_in: number }>(`/api/v1/bots/${activeBot.id}/voice-session`, token, { method: "POST" });
      const wsBase = process.env.NEXT_PUBLIC_NEXUS_API_WS_URL ?? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`;
      const socket = new WebSocket(`${wsBase}/api/v1/bots/${activeBot.id}/voice/stream?token=${encodeURIComponent(result.token)}`);
      voiceSocket.current = socket;
      socket.onopen = () => {
        setVoiceToken(result.token);
        setVoiceState("ready");
        setStatus("Voice connected. Press Start speaking for each turn.");
      };
      socket.onmessage = (message) => {
        if (typeof message.data !== "string") return;
        try {
          const event = JSON.parse(message.data) as { type: string; text?: string; audio_expected?: boolean; audio_base64?: string; content_type?: string };
          if (event.type === "transcript" && event.text) setMessages((current) => [...current, { role: "user", content: event.text! }]);
          if (event.type === "response" && event.text) {
            setMessages((current) => [...current, { role: "assistant", content: event.text! }]);
            if (!event.audio_expected && "speechSynthesis" in window) {
              const utterance = new SpeechSynthesisUtterance(event.text);
              utterance.onstart = () => setVoiceState("speaking");
              utterance.onend = () => setVoiceState("ready");
              window.speechSynthesis.speak(utterance);
            }
          }
          if (event.type === "audio_chunk" && event.audio_base64) {
            const binary = window.atob(event.audio_base64);
            voiceAudioChunks.current.push(Uint8Array.from(binary, (character) => character.charCodeAt(0)));
            setVoiceState("speaking");
          }
          if (event.type === "audio_complete") {
            const blob = new Blob(voiceAudioChunks.current.map((chunk) => chunk.slice().buffer as ArrayBuffer), { type: "audio/mpeg" });
            voiceAudioChunks.current = [];
            const audioUrl = URL.createObjectURL(blob);
            const audio = new Audio(audioUrl);
            audio.onended = () => { URL.revokeObjectURL(audioUrl); setVoiceState("ready"); };
            void audio.play().catch(() => { URL.revokeObjectURL(audioUrl); setVoiceState("ready"); });
          }
          if (event.type === "error") { setStatus(event.text ?? "Voice request failed"); setVoiceState("ready"); }
        } catch { setStatus("Received an invalid voice response"); }
      };
      socket.onerror = () => setStatus("Voice connection failed");
      socket.onclose = () => { voiceSocket.current = null; setVoiceToken(""); setVoiceState("off"); voiceStream.current?.getTracks().forEach((track) => track.stop()); };
    }
    catch (error) { setStatus(readError(error)); }
  };

  const startRecording = async () => {
    try {
      const socket = voiceSocket.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("Voice connection is not ready");
      const stream = voiceStream.current ?? await navigator.mediaDevices.getUserMedia({ audio: true });
      voiceStream.current = stream;
      const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType: type });
      recorder.ondataavailable = (event) => { if (event.data.size && socket.readyState === WebSocket.OPEN) void event.data.arrayBuffer().then((chunk) => socket.send(chunk)); };
      recorder.onstop = () => {
        const currentThread = threadId || crypto.randomUUID();
        setThreadId(currentThread);
        socket.send(JSON.stringify({ type: "end_turn", content_type: recorder.mimeType || "audio/webm", thread_id: currentThread }));
        setVoiceState("processing");
      };
      recorder.start(500);
      voiceRecorder.current = recorder;
      setVoiceState("listening");
      setStatus("Listening… press Send voice turn when you are done speaking.");
    } catch (error) { setStatus(readError(error)); }
  };

  const stopRecording = () => {
    const recorder = voiceRecorder.current;
    if (!recorder || recorder.state === "inactive") return;
    recorder.addEventListener("stop", () => { voiceRecorder.current = null; }, { once: true });
    recorder.stop();
  };

  const endVoice = () => {
    voiceRecorder.current?.stop();
    voiceSocket.current?.close();
    voiceStream.current?.getTracks().forEach((track) => track.stop());
    voiceSocket.current = null; voiceStream.current = null; voiceRecorder.current = null;
    voiceAudioChunks.current = [];
    setVoiceToken(""); setVoiceState("off"); setStatus("Voice session ended.");
  };

  const pending = useMemo(() => incomingApprovals, [incomingApprovals]);
  return <div className="workspace-grid">
    <section className="workspace-main panel-card">
      <div className="section-heading"><div><h1>{activeBot ? activeBot.name : "New chat"}</h1><p>{activeBot ? "Your workspace teammate is ready." : "Ask your team to build, investigate, or automate."}</p></div><button className="button button-primary" disabled={busy} onClick={() => void createBot()}>＋ New agent</button></div>
      {bots.length ? <div className="teammate-tabs">{bots.map((bot) => <button key={bot.id} className={`teammate-tab ${bot.id === selectedBot ? "is-active" : ""}`} onClick={() => { setSelectedBot(bot.id); setThreadId(""); setMessages([]); }}><span className="avatar avatar-green">{bot.name.slice(0, 1).toUpperCase()}</span><span><strong>{bot.name}</strong><small>{bot.model}</small></span><span className="online-dot" /></button>)}</div> : <div className="empty-state chat-empty"><h2>What will your team work on?</h2><p>Create an agent to start a conversation. It can carry context into routines and workflows.</p><form className="chat-composer chat-composer--empty" onSubmit={(event) => { event.preventDefault(); if (!token) { onConnect(); return; } const draft = text.trim(); void createBot().then((created) => { if (created && draft) void send(created.id, draft); }); }}><label className="sr-only" htmlFor="first-chat-prompt">Message for your agent</label><textarea id="first-chat-prompt" value={text} onChange={(event) => setText(event.target.value)} placeholder="Ask NexusAgent to build, fix, or explore…" rows={3} /><div><span>{token ? "Create an agent to send your first message" : "Connect a workspace to start"}</span><button className="send-button" type="submit" disabled={busy} aria-label={token ? "Create agent" : "Connect workspace"}>↑</button></div></form><button className="chat-empty__action" onClick={() => !token ? onConnect() : void createBot()}>{token ? "Create an agent" : "Connect workspace"}</button></div>}
      {activeBot && <>
        <div className="workspace-tabs"><button className={tab === "chat" ? "selected" : ""} onClick={() => setTab("chat")}>Conversation</button><button className={tab === "routines" ? "selected" : ""} onClick={() => setTab("routines")}>Routine editor <span>{routines.length}</span></button></div>
        {tab === "chat" && <div className="chat-pane"><div className="chat-toolbar"><div><strong>{activeBot.name}</strong><span> · Ready when you are</span></div><button className={`voice-toggle ${voiceToken ? "voice-active" : ""}`} onClick={() => !voiceToken ? void startVoice() : voiceState === "listening" ? stopRecording() : voiceState === "ready" ? void startRecording() : endVoice()}><span>◖</span> {!voiceToken ? "Voice mode" : voiceState === "listening" ? "Send voice turn" : voiceState === "ready" ? "Start speaking" : `Voice ${voiceState} · End`}</button></div><div className="message-list">{messages.length === 0 && <div className="welcome-note"><span className="avatar avatar-green">{activeBot.name.slice(0, 1).toUpperCase()}</span><div><strong>Hi, I’m {activeBot.name}.</strong><p>I can help with research, workflow tasks, and workspace routines. What should we work on?</p></div></div>}{messages.map((message, index) => message.role === "system" ? <div className={message.content === THINKING ? "thinking-line" : "thinking-line chat-notice"} role={message.content === THINKING ? undefined : "alert"} key={index}>{message.content === THINKING && <span className="typing-dots">•••</span>} {message.content}</div> : <div key={`${index}-${message.role}`} className={`chat-message chat-message--${message.role}`}><span className="message-avatar">{message.role === "user" ? "You" : activeBot.name.slice(0, 1)}</span><div>{message.content}</div></div>)}</div><form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(); }}><textarea value={text} onChange={(event) => setText(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="Message your teammate…" rows={2} /><div><span>↵ to send · Shift + ↵ for a new line</span><button className="send-button" disabled={!text.trim()}>↑</button></div></form></div>}
        {tab === "routines" && <div className="routines-pane"><div className="routine-editor"><div className="routine-title"><span className="routine-mark">✎</span><div><strong>New Markdown routine</strong><p>Readable instructions, predictable schedule.</p></div></div><label className="field"><span>Routine name</span><input value={routine.name} onChange={(event) => setRoutine({ ...routine, name: event.target.value })} /></label><label className="field"><span>Instructions</span><textarea rows={6} value={routine.instruction_markdown} onChange={(event) => setRoutine({ ...routine, instruction_markdown: event.target.value })} /></label><div className="schedule-row"><label className="field"><span>Schedule</span><select value={schedulePreset} onChange={(event) => { const value = event.target.value; setSchedulePreset(value); if (value === "daily") setRoutine({ ...routine, cron_expression: "0 9 * * *" }); if (value === "weekdays") setRoutine({ ...routine, cron_expression: "0 9 * * 1-5" }); if (value === "weekly") setRoutine({ ...routine, cron_expression: "0 9 * * 1" }); }}><option value="daily">Every day · 9:00</option><option value="weekdays">Weekdays · 9:00</option><option value="weekly">Weekly · Monday at 9:00</option><option value="custom">Custom cron</option></select></label><label className="field"><span>Timezone</span><input value={routine.timezone} onChange={(event) => setRoutine({ ...routine, timezone: event.target.value })} /></label></div>{schedulePreset === "custom" && <label className="field"><span>Custom cron expression</span><input value={routine.cron_expression} onChange={(event) => setRoutine({ ...routine, cron_expression: event.target.value })} placeholder="0 9 * * 1" /></label>}<div className="routine-save"><span>◇ Runs with {activeBot.name}</span><button className="button button-primary" onClick={() => void createRoutine()}>Save routine</button></div></div><div className="routine-list"><div className="routine-list-head"><h3>Scheduled routines</h3><span>{routines.length} total</span></div>{routines.filter((item) => item.bot_id === activeBot.id).map((item) => <article key={item.id} className="routine-row"><span className="routine-mark">◷</span><div><strong>{item.name}</strong><p>{item.cron_expression} · {item.timezone}</p></div><button className="button button-quiet button-small" onClick={() => void runRoutine(item.id)}>Run now</button></article>)}{routines.filter((item) => item.bot_id === activeBot.id).length === 0 && <p className="muted-copy">No routines yet. Add one with a schedule and Markdown instructions.</p>}</div></div>}
      </>}
      {status && <div className="status-strip" role="status">{status}<button onClick={() => setStatus("")}>×</button></div>}
    </section>
    <aside className="team-side panel-card"><div className="team-side__section"><div className="team-side__heading"><div><span className="eyebrow">HUMAN REVIEW</span><h3>Approval queue</h3></div><span className="queue-count">{pending.length}</span></div>{pending.length ? <div className="side-approval-queue">{pending.map((approval) => <ApprovalCard key={approval.approval_id} approval={approval} token={token} onResolved={onApprovalResolved} />)}</div> : <div className="side-empty"><strong>All caught up</strong><p>Decisions from active workflow runs will appear here.</p></div>}</div><div className="team-side__section"><div className="team-side__heading"><div><span className="eyebrow">SCHEDULED WORK</span><h3>Routines</h3></div><span className="queue-count">{routines.filter((item) => item.enabled).length}</span></div>{routines.length ? <div className="side-routine-list">{routines.map((item) => <article className="side-routine" key={item.id}><div><strong>{item.name}</strong><small>{item.cron_expression} · {item.timezone}</small></div><button className="button button-small" onClick={() => void runRoutine(item.id)}>Run</button></article>)}</div> : <div className="side-empty"><strong>No routines scheduled</strong><p>Create a Markdown routine for a teammate and its schedule will appear here.</p><button className="button button-small" onClick={() => setTab("routines")}>Create a routine</button></div>}</div><div className="side-note"><strong>Private by design</strong><p>Conversation history, routines, and approvals stay scoped to this workspace.</p></div></aside>
  </div>;
}
