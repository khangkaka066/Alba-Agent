"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TeammateWorkspace } from "@/components/teammates/teammate-workspace";
import { LearningTransferRadar } from "@/components/learning-transfer-radar";
import { FinOpsDistillationPanel } from "@/components/finops-distillation-panel";
import { IntegrationsPage } from "@/components/integrations/integrations-page";
import { ModelProvider } from "@/components/model-context";
import { ModelPicker } from "@/components/model-picker";
import { SettingsTabs } from "@/components/providers/settings-tabs";
import { FileExplorer } from "@/components/workspace/file-explorer";
import { LanguageSwitch } from "@/components/language-switch";
import { useLocale } from "@/components/locale-provider";
import { ShortcutSettings } from "@/components/providers/shortcut-settings";
import { ProviderSettings } from "@/components/providers/provider-settings";
import { NexusAgentLogo } from "@/components/brand/nexus-agent-logo";
import { TeamEvolutionOverview } from "@/components/team-evolution-overview";
import { WorkspaceApp } from "@/components/workspace/workspace-app";
import { WorkspaceProvider, useWorkspace } from "@/components/workspace/workspace-context";
import { apiRequest, readError, tokenExpiry } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";
import { actionFor, formatCombo, loadBindings, saveBindings, type Bindings } from "@/lib/shortcuts.mjs";

type WorkspaceScope = { tenant_id: string; workspace_id: string };
export type NavPage = "studio" | "settings" | "integrations" | "teammates" | "intelligence";

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
  integrations: "/settings/integrations",
  settings: "/settings/providers",
  teammates: "/teammates",
  intelligence: "/intelligence",
};


// The rail has one destination, Work, with Settings pinned at the bottom. Outputs live in the Work view and its file tree;
// integrations (channels, MCP, skills) live under Settings.
const NAV_ITEMS: Array<{ page: NavPage; icon: "studio"; action: string }> = [
  { page: "studio", icon: "studio", action: "nav-studio" },
];
const NAV_TARGETS: Record<string, NavPage> = { "nav-studio": "studio", "nav-integrations": "integrations", "nav-settings": "settings" };
// Expert pages live under Settings, so Settings stays highlighted while they are open.
const SETTINGS_FAMILY: NavPage[] = ["settings", "integrations", "teammates", "intelligence"];

function NavGlyph({ name }: { name: "studio" | "settings" }) {
  const paths: Record<typeof name, React.ReactNode> = {
    studio: <><path d="M4 5.5h16v10.5H9l-4.5 3.5V5.5z" /><path d="M8.5 10h7" /></>,
    settings: <><path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4m9.2 9.2L18 18m0-12-1.4 1.4m-9.2 9.2L6 18" /><circle cx="12" cy="12" r="4" /></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

/** Sidebar toggle and search, drawn as the two icons that sit beside the logo (and float in the corner when the sidebar is hidden). */
function HeaderButtons({ collapsed, onToggle, onSearch, toggleHint, searchHint }: { collapsed: boolean; onToggle: () => void; onSearch: () => void; toggleHint: string; searchHint: string }) {
  const { t } = useLocale();
  const icon = { className: "header-icon", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  return <div className="header-buttons">
    <button className="header-button" onClick={onToggle} aria-label={t(collapsed ? "shell.showSidebar" : "shell.hideSidebar")} aria-expanded={!collapsed} title={`${t(collapsed ? "shell.showSidebar" : "shell.hideSidebar")} (${toggleHint})`}>
      <svg {...icon}><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><path d="M9.5 5v14" /></svg></button>
    <button className="header-button" onClick={onSearch} aria-label={t("shell.search")} title={`${t("shell.search")} (${searchHint})`}>
      <svg {...icon}><circle cx="10.8" cy="10.8" r="6.2" /><path d="m15.5 15.5 4.7 4.7" /></svg></button>
  </div>;
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

function CommandPalette({ onClose, onNavigate, hint, onConnect }: { onClose: () => void; onNavigate: (page: NavPage) => void; hint: (action: string) => string; onConnect: (() => void) | null }) {
  const { t } = useLocale();
  const commands: Array<{ label: string; hint: string; run: () => void }> = [
    { label: t("palette.work"), hint: hint("nav-studio"), run: () => onNavigate("studio") },
    { label: t("page.integrations"), hint: hint("nav-integrations"), run: () => onNavigate("integrations") },
    { label: t("page.settings"), hint: hint("nav-settings"), run: () => onNavigate("settings") },
    { label: t("palette.teammates"), hint: t("palette.advanced"), run: () => onNavigate("teammates") },
    { label: t("palette.intelligence"), hint: t("palette.advanced"), run: () => onNavigate("intelligence") },
    ...(onConnect ? [{ label: t("palette.signIn"), hint: t("palette.account"), run: onConnect }] : []),
  ];
  const [query, setQuery] = useState("");
  const filtered = commands.filter((command) => command.label.toLowerCase().includes(query.toLowerCase()));
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

  const toggleSidebar = useCallback(() => setCollapsed((value) => {
    try { window.localStorage.setItem("nexus_sidebar_collapsed", value ? "0" : "1"); } catch { /* keep the in-memory choice */ }
    return !value;
  }), []);

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
      else if (NAV_TARGETS[action]) navigate(NAV_TARGETS[action]);
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [bindings, navigate, toggleSidebar]);

  const changeBindings = useCallback((next: Bindings) => { setBindings(next); saveBindings(window.localStorage, next); }, []);
  const hint = useCallback((action: string) => formatCombo(bindings[action] ?? "", mac), [bindings, mac]);
  const currentScope = useMemo(() => scope, [scope]);
  const connect = localMode === false ? () => setAccountOpen(true) : null;

  const navLink = (target: NavPage, icon: "studio" | "settings", label: string, shortcut: string) => {
    const active = target === "settings" ? SETTINGS_FAMILY.includes(page) : page === target;
    return <a key={target} href={pagePaths[target]} className={`nav-link ${active ? "is-active" : ""}`} aria-current={active ? "page" : undefined}
      onClick={(event) => { event.preventDefault(); navigate(target); }}><NavGlyph name={icon} /><span className="nav-link__label">{label}</span>{shortcut && <kbd>{shortcut}</kbd>}</a>;
  };

  return <ModelProvider token={token}><WorkspaceProvider token={token}><div className={`app-shell app-shell--chat ${collapsed ? "app-shell--collapsed" : ""} ${mobileNavOpen ? "app-shell--mobile-nav-open" : ""}`}>
    <aside className="sidebar" aria-label={t("shell.sidebar")}>
      <div className="brand-row"><a className="brand" href="/studio" onClick={(event) => { event.preventDefault(); navigate("studio"); }} aria-label="NexusAgent"><span className="brand-symbol"><NexusAgentLogo size={34} /></span><span className="brand-copy"><strong>NexusAgent</strong></span></a><HeaderButtons collapsed={collapsed} onToggle={toggleSidebar} onSearch={() => setCommandOpen(true)} toggleHint={hint("toggle-sidebar")} searchHint={hint("palette")} /></div>
      <nav className="main-nav" aria-label={t("shell.screens")}>{NAV_ITEMS.map((item) => navLink(item.page, item.icon, t(`page.${item.page}`), hint(item.action)))}</nav>
      <FileExplorer onOpened={() => navigate("studio")} />
      <div className="sidebar-bottom">{navLink("settings", "settings", t("page.settings"), hint("nav-settings"))}</div>
    </aside>
    {mobileNavOpen && <button className="mobile-nav-scrim" aria-label={t("shell.closeNav")} onClick={() => setMobileNavOpen(false)} />}
    {collapsed && <div className="header-float"><HeaderButtons collapsed onToggle={toggleSidebar} onSearch={() => setCommandOpen(true)} toggleHint={hint("toggle-sidebar")} searchHint={hint("palette")} /></div>}
    <main className="main-area">
      <header className="app-header">
        <button className="mobile-nav-toggle" aria-label={t("shell.openNav")} onClick={() => setMobileNavOpen(true)}><span /><span /><span /></button>
        <h1 className="app-header__title">{t(`page.${page}`)}</h1>
        <span className="app-header__spacer" />
        <ModelPicker onOpenSettings={() => navigate("settings")} />
        <LanguageSwitch />
        <button className="header-button" aria-label={t("shell.help")} title={t("shell.help")} onClick={() => setHelpOpen(true)}>?</button>
      </header>
      <div className={`content-area content-area--${page}`}>
        {page === "studio" && <WorkspaceApp scope={currentScope} shortcutHint={hint("toggle-canvas")} onConnect={() => setAccountOpen(true)} onModal={setModal} onNavigate={navigate} />}
        {page === "settings" && <><SettingsTabs page="settings" onNavigate={navigate} /><ProviderSettings token={token} onNavigate={navigate} /></>}
        {page === "integrations" && <><SettingsTabs page="integrations" onNavigate={navigate} /><IntegrationsPage token={token} onConnect={() => setAccountOpen(true)} /></>}
        {page === "teammates" && <TeammatesHost token={token} scope={currentScope} onConnect={() => setAccountOpen(true)} />}
        {page === "intelligence" && <><div className="page-title-row"><div><h1>{t("intelligence.title")}</h1><p>{t("intelligence.body")}</p></div></div><div className="intelligence-stack"><EvolutionHost token={token} onOpened={() => navigate("studio")} /><LearningTransferRadar token={token} /><FinOpsDistillationPanel token={token} /></div></>}
      </div>
    </main>
    {accountOpen && localMode === false && <AccountDialog token={token} scope={scope} onScope={saveScope} onToken={saveToken} onClose={() => setAccountOpen(false)} />}
    {modal && <IntegrationDialog kind={modal} token={token} onClose={() => setModal(null)} />}
    {commandOpen && <CommandPalette onClose={() => setCommandOpen(false)} onNavigate={navigate} hint={hint} onConnect={connect} />}
    {helpOpen && <ShortcutsDialog bindings={bindings} onChange={changeBindings} mac={mac} onClose={() => setHelpOpen(false)} />}
  </div></WorkspaceProvider></ModelProvider>;
}
