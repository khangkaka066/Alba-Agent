"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { TeammateWorkspace } from "@/components/teammates/teammate-workspace";
import { LearningTransferRadar } from "@/components/learning-transfer-radar";
import { FinOpsDistillationPanel } from "@/components/finops-distillation-panel";
import { CustomizePage } from "@/components/integrations/customize-page";
import { ModelProvider } from "@/components/model-context";
import { GeneralSettings } from "@/components/settings/general-settings";
import { useLocale } from "@/components/locale-provider";
import { ShortcutSettings } from "@/components/providers/shortcut-settings";
import { ProviderSettings } from "@/components/providers/provider-settings";
import { TeamEvolutionOverview } from "@/components/team-evolution-overview";
import { WorkspaceApp } from "@/components/workspace/workspace-app";
import { WorkspaceProvider, useWorkspace } from "@/components/workspace/workspace-context";
import { apiRequest, readError, tokenExpiry } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";
import { actionFor, formatCombo, loadBindings, saveBindings, type Bindings } from "@/lib/shortcuts.mjs";
import { INITIAL_DOCK, dockAfter, loadProjects, type DockTab } from "@/lib/shell.mjs";
import { Sidebar } from "@/components/shell/sidebar";
import { SettingsModal } from "@/components/shell/settings-modal";
import { ShellContext, type NavPage, type ShellValue } from "@/components/shell/shell-context";
import { TitleBar } from "@/components/shell/title-bar";
import { useConversations } from "@/components/workspace/use-conversations";
import { useReview } from "@/components/workspace/use-review";

type WorkspaceScope = { tenant_id: string; workspace_id: string };
export type { NavPage } from "@/components/shell/shell-context";

const emptyScope = { tenant_id: "", workspace_id: "" };

function AccountDialog({ token, scope, onToken, onScope, onClose }: { token: string; scope: WorkspaceScope; onToken: (value: string) => void; onScope: (value: WorkspaceScope) => void; onClose: () => void }) {
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [registering, setRegistering] = useState(false);
  const [publicSignup, setPublicSignup] = useState<boolean | null>(null);
  const [registration, setRegistration] = useState({ tenant_name: "My organization", workspace_name: "My workspace", display_name: "Workspace owner", setup_token: "" });
  useEffect(() => {
    void apiRequest<{ public_signup_enabled: boolean }>("/api/v1/auth/signup-options", "")
      .then((result) => setPublicSignup(result.public_signup_enabled))
      .catch(() => setPublicSignup(false));
  }, []);
  const signIn = async () => {
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ access_token: string; tenant_id?: string; workspace_id?: string }>(publicSignup ? "/api/v1/auth/login" : "/api/v1/auth/token", "", { method: "POST", body: JSON.stringify(publicSignup ? { email, password } : { ...scope, email, password }) });
      if (result.tenant_id && result.workspace_id) onScope({ tenant_id: result.tenant_id, workspace_id: result.workspace_id });
      onToken(result.access_token); onClose();
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  const register = async () => {
    setBusy(true); setError("");
    try {
      const result = await apiRequest<{ access_token: string; tenant_id: string; workspace_id: string }>(publicSignup ? "/api/v1/auth/signup" : "/api/v1/auth/register", "", { method: "POST", body: JSON.stringify(publicSignup ? { tenant_name: registration.tenant_name, workspace_name: registration.workspace_name, display_name: registration.display_name, email, password } : { ...registration, email, password }) });
      onScope({ tenant_id: result.tenant_id, workspace_id: result.workspace_id }); onToken(result.access_token); onClose();
    } catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  if (publicSignup === null) return <Dialog title="Connect a workspace" onClose={onClose}><p className="dialog-copy">Checking account options…</p></Dialog>;
  return <Dialog title={registering ? publicSignup ? "Create your workspace" : "Create the first workspace" : "Connect a workspace"} onClose={onClose} onSubmit={() => { if (!busy && email && password) void (registering ? register() : signIn()); }}><p className="dialog-copy">{registering ? publicSignup ? "Create an account to start your workspace. Paid model usage requires billing credit or your own provider key." : "One-time owner setup. Enter the local registration token from your .env file." : "Sign in to connect the studio to your workspace API."}</p>{registering && <><label className="field"><span>Organization</span><input value={registration.tenant_name} onChange={(event) => setRegistration({ ...registration, tenant_name: event.target.value })} /></label><label className="field"><span>Workspace</span><input value={registration.workspace_name} onChange={(event) => setRegistration({ ...registration, workspace_name: event.target.value })} /></label><label className="field"><span>Your name</span><input value={registration.display_name} onChange={(event) => setRegistration({ ...registration, display_name: event.target.value })} /></label>{!publicSignup && <label className="field"><span>Setup token</span><input type="password" value={registration.setup_token} onChange={(event) => setRegistration({ ...registration, setup_token: event.target.value })} autoComplete="off" /></label>}</>}{!registering && !publicSignup && <><label className="field"><span>Tenant ID</span><input value={scope.tenant_id} onChange={(event) => onScope({ ...scope, tenant_id: event.target.value })} placeholder="Workspace tenant UUID" /></label><label className="field"><span>Workspace ID</span><input value={scope.workspace_id} onChange={(event) => onScope({ ...scope, workspace_id: event.target.value })} placeholder="Workspace UUID" /></label></>}<label className="field"><span>Email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" /></label><label className="field"><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={registering ? "new-password" : "current-password"} /></label>{registering && <p className="dialog-copy">Use at least 12 characters for your password.</p>}{error && <p className="inline-error" role="alert">{error}</p>}<div className="dialog-actions"><button className="button button-quiet" onClick={onClose}>Cancel</button><button className="button button-quiet" onClick={() => { setRegistering(!registering); setError(""); }}>{registering ? "Sign in instead" : publicSignup ? "Create account" : "First-time setup"}</button><button className="button button-primary" disabled={busy || !email || !password || (registering ? (!publicSignup && !registration.setup_token) || password.length < 12 : !publicSignup && (!scope.tenant_id || !scope.workspace_id))} onClick={() => void (registering ? register() : signIn())}>{busy ? "Connecting…" : registering ? "Create workspace" : "Sign in"}</button></div>{token && <p className="dialog-copy">A workspace token is already stored in this browser.</p>}</Dialog>;
}

function Dialog({ title, children, onClose, onSubmit }: { title: string; children: React.ReactNode; onClose: () => void; onSubmit?: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="modal-card" role="dialog" aria-modal="true" aria-label={title} onKeyDown={(event) => { if (onSubmit && event.key === "Enter" && event.target instanceof HTMLInputElement) { event.preventDefault(); onSubmit(); } }}><header className="modal-head"><div><span className="eyebrow">NEXUSAGENT</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close dialog">×</button></header>{children}</section></div>;
}

function IntegrationDialog({ kind, token, onClose }: { kind: "api-key" | "widget"; token: string; onClose: () => void }) {
  const [key, setKey] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [copied, setCopied] = useState(false);
  const [origin, setOrigin] = useState("https://studio.example.com");
  useEffect(() => { setOrigin(window.location.origin); }, []);
  const code = kind === "widget" ? `<iframe\n  src="${origin}/embed/workflow-id"\n  title="NexusAgent Studio workflow"\n  width="100%"\n  height="640"\n></iframe>` : "";
  const generate = async () => {
    setBusy(true); setError("");
    try { const result = await apiRequest<{ key: string }>("/api/v1/auth/keys", token, { method: "POST", body: JSON.stringify({ scopes: ["read", "write", "run"] }) }); setKey(result.key); }
    catch (reason) { setError(readError(reason)); }
    finally { setBusy(false); }
  };
  const copy = async (value: string) => { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1800); };
  return <Dialog title={kind === "api-key" ? "BaaS API access" : "Embed a workflow"} onClose={onClose}>{kind === "api-key" ? <><p className="dialog-copy">Create a scoped key for server-side workflow access. This secret is shown once; keep it on a trusted server.</p>{key ? <><div className="key-reveal"><code>{key}</code><button className="button button-small" onClick={() => void copy(key)}>{copied ? "Copied" : "Copy key"}</button></div><pre className="code-sample">{`curl -X POST "$NEXUS_API_URL/api/v1/workflows/$WORKFLOW_ID/runs" \\\n  -H "X-Nexus-API-Key: $NEXUS_SERVICE_KEY" \\\n  -H "X-Nexus-Tenant-ID: $NEXUS_TENANT_ID" \\\n  -H "X-Nexus-Workspace-ID: $NEXUS_WORKSPACE_ID" \\\n  -H "Content-Type: application/json" \\\n  -d '{"input_data":{"request":"Summarize this account"}}'`}</pre></> : <button className="button button-primary" disabled={!token || busy} onClick={() => void generate()}>{busy ? "Creating key…" : "Create service key"}</button>}{error && <p className="inline-error">{error}</p>}</> : <><p className="dialog-copy">Use this iframe in an authenticated workspace surface. Your host application should establish the user session before embedding.</p><pre className="code-sample">{code}</pre><div className="dialog-actions"><span className="muted-copy">Replace workflow-id with a published workflow.</span><button className="button button-primary" onClick={() => void copy(code)}>{copied ? "Copied" : "Copy embed code"}</button></div></>}</Dialog>;
}


const pagePaths: Record<NavPage, string> = {
  studio: "/studio",
  general: "/settings",
  integrations: "/settings/integrations",
  settings: "/settings/providers",
  teammates: "/teammates",
  intelligence: "/intelligence",
};


// The rail starts with New chat, Automations and Customize above the task list, with Settings pinned at the bottom.
// Integrations (channels, MCP, skills) open from Customize.
const NAV_TARGETS: Record<string, NavPage> = { "nav-studio": "studio", "nav-integrations": "integrations", "nav-settings": "general" };
// Settings is a panel with its own navigation: General, Models and Intelligence (learning metrics).
const SETTINGS_FAMILY: NavPage[] = ["general", "settings", "intelligence"]; // shown as a panel over the work; Teammates (Automations) is a full page

type NavIcon = "studio" | "newSession" | "customize" | "general" | "models" | "teammates" | "intelligence" | "back" | "shortcuts" | "logout";

function NavGlyph({ name }: { name: NavIcon }) {
  const paths: Record<typeof name, React.ReactNode> = {
    studio: <><path d="M4 5.5h16v10.5H9l-4.5 3.5V5.5z" /><path d="M8.5 10h7" /></>,
    general: <><path d="M10.54 5.15L10.69 2.69 L13.31 2.69 L13.46 5.15A7 7 0 0 1 15.81 6.13L17.66 4.49 L19.51 6.34 L17.87 8.19A7 7 0 0 1 18.85 10.54L21.31 10.69 L21.31 13.31 L18.85 13.46A7 7 0 0 1 17.87 15.81L19.51 17.66 L17.66 19.51 L15.81 17.87A7 7 0 0 1 13.46 18.85L13.31 21.31 L10.69 21.31 L10.54 18.85A7 7 0 0 1 8.19 17.87L6.34 19.51 L4.49 17.66 L6.13 15.81A7 7 0 0 1 5.15 13.46L2.69 13.31 L2.69 10.69 L5.15 10.54A7 7 0 0 1 6.13 8.19L4.49 6.34 L6.34 4.49 L8.19 6.13A7 7 0 0 1 10.54 5.15Z" /><circle cx="12" cy="12" r="3" /></>,
    models: <path d="M12 3 20 7.5v9L12 21 4 16.5v-9zM12 12l8-4.5M12 12 4 7.5M12 12v9" />,
    teammates: <><circle cx="9" cy="8.5" r="3" /><path d="M3.5 19c.5-3 3-4.8 5.5-4.8s5 1.8 5.5 4.8M16 6a2.6 2.6 0 0 1 0 5M17.5 14.4c1.9.5 3 2.1 3.3 4.6" /></>,
    intelligence: <path d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6" />,
    back: <path d="M19 12H5M11 6l-6 6 6 6" />,
    shortcuts: <><rect x="3.5" y="6" width="17" height="12" rx="2.5" /><path d="M7.5 10h.01M12 10h.01M16.5 10h.01M8 14h8" /></>,
    logout: <path d="M10 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H10M9 12h11M16 8l4 4-4 4" />,
    newSession: <path d="M4 12 20 4l-4 16-4.5-6.5z" />,
    customize: <><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /><path d="M16.75 4v6.5M13.5 7.25H20" /></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function ShortcutsDialog({ bindings, onChange, mac, onClose }: { bindings: Bindings; onChange: (next: Bindings) => void; mac: boolean; onClose: () => void }) {
  const { t } = useLocale();
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal-card help-modal" role="dialog" aria-modal="true" aria-label={t("shell.help")}>
      <header className="modal-head"><div><span className="eyebrow">{t("shell.helpEyebrow")}</span><h2>{t("shell.shortcutsTitle")}</h2></div><button className="icon-button" aria-label={t("common.close")} onClick={onClose}>×</button></header>
      <ShortcutSettings bindings={bindings} onChange={onChange} mac={mac} />
    </section>
  </div>;
}

function CommandPalette({ onClose, onNavigate, hint, onConnect, extra }: { onClose: () => void; onNavigate: (page: NavPage) => void; hint: (action: string) => string; onConnect: (() => void) | null; extra: Array<{ label: string; hint: string; run: () => void }> }) {
  const { t } = useLocale();
  const commands: Array<{ label: string; hint: string; run: () => void }> = [
    { label: t("palette.work"), hint: hint("nav-studio"), run: () => onNavigate("studio") },
    { label: t("page.integrations"), hint: hint("nav-integrations"), run: () => onNavigate("integrations") },
    { label: t("page.settings"), hint: hint("nav-settings"), run: () => onNavigate("general") },
    { label: t("shell.automations"), hint: t("palette.advanced"), run: () => onNavigate("teammates") },
    { label: t("palette.intelligence"), hint: t("palette.advanced"), run: () => onNavigate("intelligence") },
    ...(onConnect ? [{ label: t("palette.signIn"), hint: t("palette.account"), run: onConnect }] : []),
    ...extra,
  ];
  const [query, setQuery] = useState("");
  const filtered = commands.filter((command) => command.label.toLowerCase().includes(query.toLowerCase())).slice(0, 14);
  return <div className="command-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="command-palette" role="dialog" aria-modal="true" aria-label={t("shell.search")}><label className="command-search"><span aria-hidden="true">⌕</span><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("palette.placeholder")} /></label><div className="command-list">{filtered.map((command) => <button key={command.label} onClick={() => { command.run(); onClose(); }}><span>{command.label}</span><kbd>{command.hint}</kbd></button>)}{filtered.length === 0 && <p>{t("palette.empty")}</p>}</div><footer><span>{t("palette.footer")}</span><kbd>ESC</kbd></footer></section></div>;
}

function EvolutionHost({ token, onOpened }: { token: string; onOpened: () => void }) {
  const workspace = useWorkspace();
  return <TeamEvolutionOverview token={token} onOpen={(id) => { workspace.openWorkflow(id); onOpened(); }} />;
}

function TeammatesHost({ token, scope, onConnect }: { token: string; scope: WorkspaceScope; onConnect: () => void }) {
  const workspace = useWorkspace();
  return <TeammateWorkspace token={token} scope={scope} incomingApprovals={workspace.run.approvals} onApprovalResolved={workspace.dismissApproval} onConnect={onConnect} />;
}

/** The signed-in account at the foot of the sidebar; it opens a small menu with Settings, Shortcuts and Log out. */
function AccountRow({ token, inSettings, onSettings, onClose, onShortcuts, onLogout }: { token: string; inSettings: boolean; onSettings: () => void; onClose: () => void; onShortcuts: () => void; onLogout: (() => void) | null }) {
  const { t } = useLocale();
  const [account, setAccount] = useState<{ email: string; display_name: string } | null>(null);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!token) { setAccount(null); return; }
    let stopped = false;
    void apiRequest<{ email: string; display_name: string }>("/api/v1/auth/me", token).then((value) => { if (!stopped) setAccount(value); }).catch(() => undefined);
    return () => { stopped = true; };
  }, [token]);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", escape); };
  }, [open]);
  const label = account?.email || account?.display_name || t("account.signedOut");
  const choose = (run: () => void) => () => { setOpen(false); run(); };
  const item = (icon: NavIcon, text: string, run: () => void) => <button type="button" role="menuitem" className="account-menu__item" onClick={choose(run)}><NavGlyph name={icon} /><span>{text}</span></button>;
  return <div className="account-wrap" ref={root}>
    {open && <div className="account-menu" role="menu" aria-label={t("account.open")}>
      {inSettings ? item("general", t("account.menu.close"), onClose) : item("general", t("page.settings"), onSettings)}
      <div className="account-menu__rule" />
      {item("shortcuts", t("shell.shortcutsTitle"), onShortcuts)}
      {onLogout && <><div className="account-menu__rule" />{item("logout", t("account.menu.logout"), onLogout)}</>}
    </div>}
    <button type="button" className={`account-row ${open ? "is-active" : ""}`} aria-haspopup="menu" aria-expanded={open} title={t("account.open")} aria-label={t("account.open")} onClick={() => setOpen((value) => !value)}>
      <span className="account-avatar" aria-hidden="true">{(account?.display_name || account?.email || "?").charAt(0).toUpperCase()}</span>
      <span className="account-email">{label}</span>
    </button>
  </div>;
}

type LocalSession = { access_token: string; tenant_id: string; workspace_id: string; expires_in: number };

export function StudioApp({ initialPage = "studio" }: { initialPage?: NavPage }) {
  const { t } = useLocale();
  const [page, setPage] = useState<NavPage>(initialPage);
  useEffect(() => { document.title = `${t(`page.${page}`)} · NexusAgent`; }, [page, t]);
  const [token, setToken] = useState("");
  const [scope, setScope] = useState<WorkspaceScope>(emptyScope);
  const [localMode, setLocalMode] = useState<boolean | null>(null); // null while the server is asked
  const [accountOpen, setAccountOpen] = useState(false);
  const [modal, setModal] = useState<"api-key" | "widget" | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [bindings, setBindings] = useState<Bindings>(() => loadBindings({ getItem: () => null }));
  const [mac, setMac] = useState(false);

  const navigate = useCallback((next: NavPage) => {
    setPage(next);
    setMobileNavOpen(false);
    if (typeof window !== "undefined" && window.location.pathname !== pagePaths[next]) window.history.pushState({}, "", pagePaths[next]);
  }, []);

  const saveToken = useCallback((value: string) => { setToken(value); window.localStorage.setItem("nexus_access_token", value); }, []);
  const saveScope = useCallback((value: WorkspaceScope) => { setScope(value); window.localStorage.setItem("nexus_tenant_id", value.tenant_id); window.localStorage.setItem("nexus_workspace_id", value.workspace_id); }, []);

  useEffect(() => {
    setPage(initialPage);
    setBindings(loadBindings(window.localStorage));
    try { setCollapsed(window.localStorage.getItem("nexus_sidebar_collapsed") === "1"); } catch { /* storage can be blocked; the sidebar then starts open */ }
    setMac(/Mac|iPhone|iPad/.test(window.navigator.platform));
    const desktop = getDesktop();
    if (desktop) document.documentElement.dataset.desktop = desktop.platform; // lets the CSS leave room for native window controls
    const savedTheme = window.localStorage.getItem("nexus_theme");
    if (savedTheme === "light" || savedTheme === "dark") setTheme(savedTheme);
    const modalEvent = (event: Event) => setModal((event as CustomEvent<"api-key" | "widget">).detail);
    const back = () => {
      const match = (Object.entries(pagePaths) as Array<[NavPage, string]>).find(([, href]) => href === window.location.pathname);
      if (match) setPage(match[0]);
    };
    window.addEventListener("nexus:modal", modalEvent);
    window.addEventListener("popstate", back);
    return () => { window.removeEventListener("nexus:modal", modalEvent); window.removeEventListener("popstate", back); };
  }, [initialPage]);

  useEffect(() => { document.documentElement.dataset.theme = theme; window.localStorage.setItem("nexus_theme", theme); }, [theme]);

  // Local mode: the server hands out the built-in owner session, so nothing ever asks the user to sign in.
  const mintRef = useRef<(() => Promise<void>) | null>(null);
  useEffect(() => {
    let stopped = false; let timer: number | undefined;
    const mint = async () => {
      const session = await apiRequest<LocalSession>("/api/v1/auth/local-session", "", { method: "POST" });
      if (stopped) return;
      saveToken(session.access_token); saveScope({ tenant_id: session.tenant_id, workspace_id: session.workspace_id });
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void mint().catch(() => undefined), Math.max(60, session.expires_in - 90) * 1000);
    };
    mintRef.current = mint;
    void (async () => {
      try {
        const mode = await apiRequest<{ enabled: boolean }>("/api/v1/auth/local-mode", "");
        if (stopped) return;
        setLocalMode(mode.enabled);
        if (mode.enabled) await mint();
        else { setToken(window.localStorage.getItem("nexus_access_token") ?? ""); const tenant = window.localStorage.getItem("nexus_tenant_id") ?? ""; const workspace = window.localStorage.getItem("nexus_workspace_id") ?? ""; if (tenant || workspace) setScope({ tenant_id: tenant, workspace_id: workspace }); }
      } catch { if (!stopped) setLocalMode(false); }
    })();
    return () => { stopped = true; window.clearTimeout(timer); mintRef.current = null; };
  }, [saveToken, saveScope]);

  // The API client renews a lost local session on its own and announces it; adopt it so every screen uses the new token.
  useEffect(() => {
    const adopt = (event: Event) => {
      const session = (event as CustomEvent<LocalSession>).detail;
      saveToken(session.access_token); saveScope({ tenant_id: session.tenant_id, workspace_id: session.workspace_id });
    };
    window.addEventListener("nexus:session-refreshed", adopt);
    return () => window.removeEventListener("nexus:session-refreshed", adopt);
  }, [saveToken, saveScope]);

  useEffect(() => {
    if (localMode === false && !token) setAccountOpen(true); // a shared server still needs a real sign-in
  }, [localMode, token]);
  useEffect(() => {
    const expire = () => { if (mintRef.current) void mintRef.current().catch(() => undefined); else { saveToken(""); setAccountOpen(true); } };
    window.addEventListener("nexus:session-expired", expire);
    const expiry = token && localMode === false ? tokenExpiry(token) : null;
    const timer = expiry === null ? undefined : window.setTimeout(expire, Math.max(0, Math.min(expiry - Date.now(), 2_000_000_000)));
    return () => { window.removeEventListener("nexus:session-expired", expire); if (timer !== undefined) window.clearTimeout(timer); };
  }, [token, localMode, saveToken]);

  const toggleSidebar = useCallback(() => {
    if (window.innerWidth <= 800) { setMobileNavOpen((value) => !value); return; } // narrow windows use the sidebar as a drawer
    setCollapsed((value) => {
      try { window.localStorage.setItem("nexus_sidebar_collapsed", value ? "0" : "1"); } catch { /* keep the in-memory choice */ }
      return !value;
    });
  }, []);

  const [dock, dispatchDock] = useReducer(dockAfter, INITIAL_DOCK);
  const [inspector, setInspector] = useState(false);
  const showDock = useCallback((tab: DockTab) => dispatchDock({ type: "show", tab }), []);
  const toggleInspector = useCallback(() => { setInspector((value) => !value); dispatchDock({ type: "show", tab: "canvas" }); }, []);
  const closeSettings = useCallback(() => navigate("studio"), [navigate]);

  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setCommandOpen(false); setMobileNavOpen(false); setAccountOpen(false); setHelpOpen(false); return; }
      if (event.target instanceof HTMLElement && event.target.dataset.shortcutCapture) return;
      const action = actionFor(bindings, event);
      if (!action) return;
      event.preventDefault();
      if (action === "palette") setCommandOpen(true);
      else if (action === "toggle-sidebar") toggleSidebar();
      else if (action === "run") window.dispatchEvent(new CustomEvent("nexus:run"));
      else if (action === "toggle-canvas") window.dispatchEvent(new CustomEvent("nexus:toggle-canvas"));
      else if (action === "toggle-dock") dispatchDock({ type: "toggle" });
      else if (action === "toggle-inspector") toggleInspector();
      else if (action === "focus-composer") { if (page !== "studio") navigate("studio"); window.setTimeout(() => window.dispatchEvent(new CustomEvent("nexus:focus-composer")), 0); }
      else if (NAV_TARGETS[action]) navigate(NAV_TARGETS[action]);
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [bindings, navigate, page, toggleSidebar, toggleInspector]);

  const changeBindings = useCallback((next: Bindings) => { setBindings(next); saveBindings(window.localStorage, next); }, []);
  const hint = useCallback((action: string) => formatCombo(bindings[action] ?? "", mac), [bindings, mac]);
  const currentScope = useMemo(() => scope, [scope]);
  const connect = localMode === false ? () => setAccountOpen(true) : null;
  const logout = localMode === false && token ? () => { saveToken(""); setAccountOpen(true); } : null;

  return <ModelProvider token={token}><WorkspaceProvider token={token}>
    <Frame page={page} navigate={navigate} collapsed={collapsed} mobileNavOpen={mobileNavOpen} closeNav={() => setMobileNavOpen(false)} toggleSidebar={toggleSidebar}
      dock={dock} dispatchDock={dispatchDock} showDock={showDock} inspector={inspector} toggleInspector={toggleInspector} hint={hint}
      openPalette={() => setCommandOpen(true)} commandOpen={commandOpen} closePalette={() => setCommandOpen(false)} connect={connect}
      token={token} scope={currentScope} accountOpen={accountOpen && localMode === false} setAccountOpen={setAccountOpen} saveScope={saveScope} saveToken={saveToken}
      modal={modal} setModal={setModal} helpOpen={helpOpen} setHelpOpen={setHelpOpen} bindings={bindings} changeBindings={changeBindings} mac={mac}
      theme={theme} setTheme={setTheme} onLogout={logout} closeSettings={closeSettings} />
  </WorkspaceProvider></ModelProvider>;
}

type FrameProps = {
  page: NavPage; navigate: (page: NavPage) => void; collapsed: boolean; mobileNavOpen: boolean; closeNav: () => void; toggleSidebar: () => void;
  dock: ShellValue["dock"]; dispatchDock: (action: Parameters<typeof dockAfter>[1]) => void; showDock: (tab: DockTab) => void; inspector: boolean; toggleInspector: () => void;
  hint: (action: string) => string; openPalette: () => void; commandOpen: boolean; closePalette: () => void; connect: (() => void) | null;
  token: string; scope: WorkspaceScope; accountOpen: boolean; setAccountOpen: (open: boolean) => void; saveScope: (value: WorkspaceScope) => void; saveToken: (value: string) => void;
  modal: "api-key" | "widget" | null; setModal: (kind: "api-key" | "widget" | null) => void; helpOpen: boolean; setHelpOpen: (open: boolean) => void;
  bindings: Bindings; changeBindings: (next: Bindings) => void; mac: boolean; theme: "dark" | "light"; setTheme: (value: "dark" | "light") => void;
  onLogout: (() => void) | null; closeSettings: () => void;
};

/** The window: title bar on top; sidebar, the work and the right dock below; settings as a panel over everything. Lives inside the workspace providers. */
function Frame(props: FrameProps) {
  const { t } = useLocale();
  const { page, navigate, token, scope, dock, showDock, dispatchDock, openPalette, hint, inspector, toggleInspector } = props;
  const workspace = useWorkspace();
  const { conversations, reload } = useConversations();
  const review = useReview();
  const inSettings = SETTINGS_FAMILY.includes(page);
  const shownPage: NavPage = inSettings ? "studio" : page;

  const value = useMemo<ShellValue>(() => ({
    dock, showDock, toggleDock: () => dispatchDock({ type: "toggle" }), closeDock: () => dispatchDock({ type: "close" }), expandDock: () => dispatchDock({ type: "expand" }),
    navigate, openPalette, hint, review, inspector, toggleInspector,
  }), [dock, showDock, dispatchDock, navigate, openPalette, hint, review, inspector, toggleInspector]);

  const current = conversations.find((item) => item.run.id === workspace.runId);
  const firstWords = workspace.messages.find((message) => message.role === "user")?.text ?? null;
  const [projects, setProjects] = useState<Record<string, string>>({});
  useEffect(() => { try { setProjects(loadProjects(window.localStorage)); } catch { setProjects({}); } }, [conversations]);
  const project = workspace.runId ? projects[workspace.runId] ?? null : null;
  const start = () => { workspace.newTask(); navigate("studio"); window.setTimeout(() => window.dispatchEvent(new Event("nexus:focus-composer")), 0); };

  const palette = [
    { label: t("shell.newConversation"), hint: t("shell.conversations"), run: start },
    { label: t("dock.review"), hint: hint("toggle-dock"), run: () => showDock("review") },
    { label: t("dock.files"), hint: hint("toggle-dock"), run: () => showDock("files") },
    { label: t("dock.terminal"), hint: hint("toggle-dock"), run: () => showDock("terminal") },
    { label: t("dock.browser"), hint: hint("toggle-dock"), run: () => showDock("browser") },
    { label: t("dock.canvas"), hint: hint("toggle-canvas"), run: () => showDock("canvas") },
    ...conversations.slice(0, 8).map((item) => ({ label: item.name, hint: t("shell.conversations"), run: () => { if (item.run.id !== workspace.runId) workspace.openRun(item.run.workflow_id, item.run.id, item.name); navigate("studio"); } })),
  ];

  const account = <AccountRow token={token} inSettings={inSettings} onSettings={() => navigate("general")} onClose={props.closeSettings} onShortcuts={() => props.setHelpOpen(true)} onLogout={props.onLogout} />;
  return <ShellContext.Provider value={value}><div className={`app-shell app-shell--chat ag-app ${props.collapsed ? "is-collapsed" : ""} ${props.mobileNavOpen ? "is-nav-open" : ""}`}>
    <TitleBar page={shownPage} title={current?.name ?? firstWords ?? ""} project={project} collapsed={props.collapsed} onToggleSidebar={props.toggleSidebar} review={review} onShortcuts={() => props.setHelpOpen(true)} onNewConversation={start} />
    <div className="ag-body">
      <Sidebar page={page} conversations={conversations} reload={reload} navigate={navigate} footer={account} onOpenSettings={() => navigate("general")} />
      {props.mobileNavOpen && <button className="ag-scrim" aria-label={t("shell.closeNav")} onClick={props.closeNav} />}
      <main className="ag-main">
        {shownPage === "studio"
          ? <div className="ag-studio"><WorkspaceApp scope={scope} onModal={props.setModal} onNavigate={navigate} /></div>
          : <div className={`content-area content-area--${shownPage}`}>
            {shownPage === "integrations" && <CustomizePage token={token} onConnect={() => props.setAccountOpen(true)} />}
            {shownPage === "teammates" && <TeammatesHost token={token} scope={scope} onConnect={() => props.setAccountOpen(true)} />}
          </div>}
      </main>
    </div>
    {inSettings && <SettingsModal page={page} navigate={navigate} onClose={props.closeSettings} onShortcuts={() => props.setHelpOpen(true)} footer={account}>
      {page === "general" && <GeneralSettings theme={props.theme} onTheme={props.setTheme} bindings={props.bindings} onBindings={props.changeBindings} mac={props.mac} />}
      {page === "settings" && <ProviderSettings token={token} onNavigate={navigate} />}
      {page === "intelligence" && <><div className="page-title-row"><div><h1>{t("intelligence.title")}</h1><p>{t("intelligence.body")}</p></div></div><div className="intelligence-stack"><EvolutionHost token={token} onOpened={() => navigate("studio")} /><LearningTransferRadar token={token} /><FinOpsDistillationPanel token={token} /></div></>}
    </SettingsModal>}
    {props.accountOpen && <AccountDialog token={token} scope={scope} onScope={props.saveScope} onToken={props.saveToken} onClose={() => props.setAccountOpen(false)} />}
    {props.modal && <IntegrationDialog kind={props.modal} token={token} onClose={() => props.setModal(null)} />}
    {props.commandOpen && <CommandPalette onClose={props.closePalette} onNavigate={navigate} hint={props.hint} onConnect={props.connect} extra={palette} />}
    {props.helpOpen && <ShortcutsDialog bindings={props.bindings} onChange={props.changeBindings} mac={props.mac} onClose={() => props.setHelpOpen(false)} />}
  </div></ShellContext.Provider>;
}
