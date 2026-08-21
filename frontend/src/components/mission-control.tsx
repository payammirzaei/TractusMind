"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  Bot,
  Command,
  Database,
  Gauge,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Search,
  SearchCode,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChatWorkbench } from "@/components/chat-workbench";
import { CommandCenter } from "@/components/command-center";
import { DataDeck } from "@/components/data-deck";
import type { Identity, UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

export type MissionView = "chat" | "overview" | "sources" | "ops" | "quality" | "admin";

type HealthCheck = "ok" | "error";
type SystemHealth = {
  status: "ok" | "degraded";
  checks: {
    postgres: HealthCheck;
    redis: HealthCheck;
    qdrant: HealthCheck;
  };
};

type NavItem = {
  view: MissionView;
  href: string;
  label: string;
  description: string;
  icon: typeof Bot;
  minimum: UserRole;
};

const NAV: NavItem[] = [
  { view: "chat", href: "/", label: "Copilot", description: "Ask grounded engineering questions and inspect evidence", icon: Bot, minimum: "user" },
  { view: "overview", href: "/overview", label: "Overview", description: "See live health, coverage, ingestion and quality signals", icon: LayoutDashboard, minimum: "operator" },
  { view: "sources", href: "/sources", label: "Sources", description: "Inspect versioned repositories, refs and indexed snapshots", icon: Database, minimum: "operator" },
  { view: "ops", href: "/ops", label: "Operations", description: "Watch ingestion health, synchronization and run telemetry", icon: Gauge, minimum: "operator" },
  { view: "quality", href: "/quality", label: "Quality", description: "Review failures and promote guarded regression cases", icon: ShieldCheck, minimum: "operator" },
  { view: "admin", href: "/admin", label: "Access", description: "Manage local identities, roles and API credentials", icon: Users, minimum: "admin" },
];

const roleRank: Record<UserRole, number> = { user: 0, operator: 1, admin: 2 };

const AUTH_ERRORS: Record<string, string> = {
  sso_not_configured: "Enterprise SSO is not configured for this Mission Control.",
  sso_unavailable: "Enterprise SSO is temporarily unavailable. You can retry or use your local account.",
  provider_rejected: "The identity provider did not complete sign-in.",
  invalid_sso_state: "The SSO transaction could not be verified. Start sign-in again.",
  token_exchange_failed: "The identity provider could not exchange the authorization code.",
  invalid_access_token: "The identity provider returned an invalid access token.",
  identity_rejected: "The signed-in identity was rejected by TractusMind access policy.",
};

function LoginConsole({ onReady, returnTo }: { onReady: (identity: Identity) => void; returnTo: string }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/oidc/status", { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : { enabled: false })
      .then((payload) => { if (!cancelled) setSsoEnabled(payload.enabled === true); })
      .catch(() => { if (!cancelled) setSsoEnabled(false); });

    const url = new URL(window.location.href);
    const authError = url.searchParams.get("auth_error");
    if (authError) {
      setError(AUTH_ERRORS[authError] ?? "Enterprise sign-in could not be completed.");
      url.searchParams.delete("auth_error");
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
    return () => { cancelled = true; };
  }, []);

  async function signIn() {
    if (!username.trim() || !password) return;
    setPending(true); setError(null);
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Sign-in rejected");
      setPassword("");
      onReady(payload as Identity);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication failed");
    } finally { setPending(false); }
  }

  return (
    <main className="grid min-h-screen place-items-center p-5">
      <motion.div initial={{ opacity: 0, scale: .98, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} className="tm-shell relative w-full max-w-[540px] rounded-[28px] p-3">
        <span className="tm-screw absolute left-4 top-4"/><span className="tm-screw absolute right-4 top-4"/><span className="tm-screw absolute bottom-4 left-4"/><span className="tm-screw absolute bottom-4 right-4"/>
        <div className="tm-well tm-scanline rounded-[20px] px-6 py-8 sm:px-9">
          <div className="mb-8 flex items-center gap-4">
            <div className="tm-control grid size-12 place-items-center rounded-2xl border-cyan-300/15"><Sparkles className="size-5 text-cyan-200"/></div>
            <div><div className="tm-label">TractusMind</div><h1 className="mt-1 text-xl font-semibold tracking-tight">Mission Control</h1></div>
          </div>
          <Badge className="mb-5 border-emerald-300/15 text-emerald-300"><span className="tm-led"/> secure console</Badge>
          <h2 className="text-3xl font-semibold tracking-[-.035em]">Engineering intelligence,<br/><span className="text-slate-500">with the panels open.</span></h2>
          <p className="mt-4 text-sm leading-6 text-slate-500">Local accounts and enterprise identities are validated by the backend. Browser credentials become an HttpOnly Mission Control session and never enter client storage.</p>

          {ssoEnabled && <div className="mt-8">
            <a href={`/api/oidc/login?return_to=${encodeURIComponent(returnTo || "/")}`} className="tm-control flex h-12 w-full items-center justify-center gap-3 rounded-xl border-cyan-300/15 text-sm font-semibold text-cyan-100 hover:border-cyan-300/30"><ShieldCheck className="size-4 text-cyan-300"/>Continue with Enterprise SSO<ArrowRight className="size-4 text-slate-600"/></a>
            <div className="mt-3 text-center text-[10px] leading-5 text-slate-600">Authorization Code + PKCE · backend role validation · no browser token storage</div>
            <div className="my-6 flex items-center gap-3"><span className="h-px flex-1 bg-white/5"/><span className="tm-label">local account</span><span className="h-px flex-1 bg-white/5"/></div>
          </div>}

          <div className={ssoEnabled ? "" : "mt-8"}>
            <label className="tm-label mb-2 block">Username</label>
            <div className="tm-well flex items-center gap-2 rounded-xl p-2">
              <Users className="ml-2 size-4 text-slate-600"/>
              <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="payam" autoComplete="username" className="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-slate-700"/>
            </div>
            <label className="tm-label mb-2 mt-4 block">Password</label>
            <div className="tm-well flex items-center gap-2 rounded-xl p-2">
              <KeyRound className="ml-2 size-4 text-slate-600"/>
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void signIn(); }} placeholder="••••••••••••" autoComplete="current-password" className="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-slate-700"/>
            </div>
            <Button variant="primary" className="mt-4 w-full" onClick={() => void signIn()} disabled={pending || !username.trim() || !password}>{pending ? "Signing in…" : "Sign in"}</Button>
            {error && <div className="mt-3 rounded-lg border border-red-300/15 bg-red-300/5 p-3 text-xs leading-5 text-red-200">{error}</div>}
          </div>
          <div className="mt-8 flex items-center justify-between border-t border-white/5 pt-4 text-[10px] uppercase tracking-[.14em] text-slate-700"><span>{ssoEnabled ? "OIDC PKCE / password" : "local password"}</span><span>RBAC aware</span><span>HttpOnly session</span></div>
        </div>
      </motion.div>
    </main>
  );
}

function BootPanel() {
  return <main className="grid min-h-screen place-items-center"><div className="flex items-center gap-3"><span className="tm-led cyan"/><span className="tm-label">initializing mission control</span></div></main>;
}

function HealthPanel({ health, reachable }: { health: SystemHealth | null; reachable: boolean }) {
  const state = !reachable ? "offline" : health?.status ?? "checking";
  const led = state === "degraded" ? "amber" : state === "offline" ? "red" : state === "checking" ? "cyan" : "";
  const checks: Array<[keyof SystemHealth["checks"], string]> = [["postgres", "Postgres"], ["redis", "Redis"], ["qdrant", "Qdrant"]];
  return (
    <div className="tm-well rounded-xl p-3" aria-live="polite">
      <div className="flex items-center gap-2"><span className={`tm-led ${led}`}/><span className="tm-label">Core {state}</span></div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-slate-600">{checks.map(([key, label]) => { const check = health?.checks[key]; return <div key={key} className="contents"><span>{label}</span><span className={cn("text-right", check === "ok" ? "text-emerald-300" : check === "error" ? "text-red-300" : "text-slate-500")}>{check ?? "—"}</span></div>; })}</div>
    </div>
  );
}

function CommandLauncher({ open, query, setQuery, items, activeView, health, healthReachable, identity, onClose, onNavigate }: {
  open: boolean;
  query: string;
  setQuery: (value: string) => void;
  items: NavItem[];
  activeView: MissionView;
  health: SystemHealth | null;
  healthReachable: boolean;
  identity: Identity;
  onClose: () => void;
  onNavigate: (href: string) => void;
}) {
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => !needle || `${item.label} ${item.description}`.toLowerCase().includes(needle));
  }, [items, query]);
  if (!open) return null;
  const healthState = !healthReachable ? "offline" : health?.status ?? "checking";
  return (
    <div className="tm-command-backdrop fixed inset-0 z-[100] grid place-items-start px-3 pt-[10vh] sm:pt-[14vh]" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <motion.div initial={{ opacity: 0, y: -12, scale: .985 }} animate={{ opacity: 1, y: 0, scale: 1 }} className="tm-command w-full max-w-[660px] rounded-[22px] p-3">
        <div className="tm-search flex h-12 items-center gap-3 rounded-xl px-4"><Search className="size-4 text-cyan-300"/><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && filtered[0]) onNavigate(filtered[0].href); }} placeholder="Jump to a Mission Control surface…" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-700"/><span className="hidden rounded-md border border-white/7 px-2 py-1 font-mono text-[9px] text-slate-600 sm:inline">ESC</span><button onClick={onClose} className="text-slate-600 hover:text-slate-300 sm:hidden"><X className="size-4"/></button></div>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_180px]">
          <div className="space-y-1">
            <div className="tm-label px-2 pb-1">surfaces</div>
            {filtered.map((item) => { const Icon = item.icon; const active = item.view === activeView; return <button key={item.view} onClick={() => onNavigate(item.href)} className={cn("tm-command-item flex w-full items-center gap-3 rounded-xl p-3 text-left", active && "is-active")}><div className="tm-control grid size-9 shrink-0 place-items-center rounded-lg"><Icon className="size-4 text-cyan-200"/></div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-xs font-semibold text-slate-200">{item.label}</span>{active && <Badge className="text-cyan-300">current</Badge>}</div><div className="mt-1 truncate text-[10px] text-slate-600">{item.description}</div></div><ArrowRight className="size-3.5 text-slate-700"/></button>; })}
            {filtered.length === 0 && <div className="rounded-xl border border-dashed border-white/6 p-6 text-center text-xs text-slate-700">No Mission Control surface matches.</div>}
          </div>
          <div className="tm-well h-fit rounded-xl p-3"><div className="tm-label">session</div><div className="mt-3 flex items-center gap-2"><span className={cn("tm-led", healthState === "degraded" && "amber", healthState === "offline" && "red", healthState === "checking" && "cyan")}/><span className="text-xs font-semibold">Core {healthState}</span></div><div className="mt-4 space-y-2 text-[10px] text-slate-600"><div className="flex justify-between"><span>identity</span><span className="max-w-[95px] truncate text-slate-400">{identity.display_name}</span></div><div className="flex justify-between"><span>role</span><span className="text-cyan-200">{identity.role}</span></div><div className="flex justify-between"><span>auth</span><span className="text-slate-400">{identity.auth_type}</span></div></div><div className="mt-4 border-t border-white/5 pt-3 text-[9px] leading-4 text-slate-700">Ctrl/⌘ K opens this launcher from anywhere.</div></div>
        </div>
      </motion.div>
    </div>
  );
}

export function MissionControl({ view }: { view: MissionView }) {
  const pathname = usePathname();
  const router = useRouter();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthReachable, setHealthReachable] = useState(true);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");

  useEffect(() => {
    fetch("/api/session", { cache: "no-store" })
      .then(async (response) => response.ok ? setIdentity(await response.json()) : setIdentity(null))
      .catch(() => setIdentity(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!identity) return;
    let cancelled = false;

    async function revalidateIdentity() {
      try {
        const response = await fetch("/api/session", { cache: "no-store" });
        if (cancelled) return;
        if (response.ok) {
          setIdentity(await response.json() as Identity);
        } else if (response.status === 401 || response.status === 403) {
          setIdentity(null);
        }
      } catch {
        // Keep the last validated identity during transient frontend/API outages.
      }
    }

    const onFocus = () => void revalidateIdentity();
    const timer = window.setInterval(() => void revalidateIdentity(), 60_000);
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [identity?.user_id]);

  useEffect(() => {
    let cancelled = false;
    async function loadHealth() {
      try {
        const response = await fetch("/api/backend/health/ready", { cache: "no-store" });
        const payload = await response.json();
        const valid = payload && typeof payload === "object" && "status" in payload && "checks" in payload;
        if (cancelled) return;
        if (valid) { setHealth(payload as SystemHealth); setHealthReachable(true); }
        else { setHealth(null); setHealthReachable(false); }
      } catch { if (!cancelled) { setHealth(null); setHealthReachable(false); } }
    }
    void loadHealth();
    const timer = window.setInterval(() => void loadHealth(), 15_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        event.stopImmediatePropagation();
        setCommandQuery("");
        setCommandOpen((value) => !value);
      }
      if (event.key === "Escape") setCommandOpen(false);
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);

  async function logout() {
    await fetch("/api/session", { method: "DELETE" });
    setIdentity(null);
  }

  if (loading) return <BootPanel />;
  if (!identity) return <LoginConsole onReady={setIdentity} returnTo={pathname || "/"} />;

  const permitted = NAV.filter((item) => roleRank[identity.role] >= roleRank[item.minimum]);
  if (!permitted.some((item) => item.view === view)) {
    return <main className="grid min-h-screen place-items-center"><div className="tm-panel rounded-2xl p-8 text-center"><ShieldCheck className="mx-auto mb-3 size-6 text-amber-300"/><h1 className="font-semibold">Insufficient role</h1><p className="mt-2 text-sm text-slate-500">This console requires elevated TractusMind access.</p><Link href="/"><Button className="mt-5">Back to copilot</Button></Link></div></main>;
  }

  const healthState = !healthReachable ? "offline" : health?.status ?? "checking";
  const healthBadgeClass = healthState === "ok" ? "text-emerald-300" : healthState === "degraded" ? "text-amber-300" : healthState === "offline" ? "text-red-300" : "text-cyan-300";
  const healthLedClass = healthState === "degraded" ? "amber" : healthState === "offline" ? "red" : healthState === "checking" ? "cyan" : "";
  const current = NAV.find((item) => item.view === view)!;

  function navigate(href: string) {
    setCommandOpen(false);
    setCommandQuery("");
    router.push(href);
  }

  return (
    <main className="h-screen overflow-hidden p-2 sm:p-3">
      <div className="tm-shell relative flex h-full overflow-hidden rounded-[24px] p-2">
        <span className="tm-screw absolute left-2 top-2"/><span className="tm-screw absolute right-2 top-2"/><span className="tm-screw absolute bottom-2 left-2"/><span className="tm-screw absolute bottom-2 right-2"/>
        <aside className="tm-desktop-only flex w-[224px] shrink-0 flex-col px-2 py-3">
          <div className="mb-5 flex items-center gap-3 px-2"><div className="tm-control grid size-10 place-items-center rounded-xl"><SearchCode className="size-4 text-cyan-200"/></div><div><div className="text-sm font-bold tracking-tight">TractusMind</div><div className="tm-label mt-1">Mission Control</div></div></div>
          <button onClick={() => { setCommandQuery(""); setCommandOpen(true); }} className="tm-search mb-5 flex h-9 items-center gap-2 rounded-lg px-3 text-left"><Command className="size-3.5 text-cyan-300"/><span className="flex-1 text-[10px] text-slate-600">Command launcher</span><span className="rounded border border-white/6 px-1.5 py-0.5 font-mono text-[8px] text-slate-700">⌘K</span></button>
          <nav className="space-y-1">{permitted.map((item) => { const active = pathname === item.href; const Icon = item.icon; return <Link key={item.view} href={item.href} className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-semibold text-slate-500 transition", active ? "tm-well text-cyan-200" : "hover:bg-white/[.03] hover:text-slate-200")}><Icon className="size-4"/><span>{item.label}</span>{active && <span className="ml-auto tm-led cyan"/>}</Link>; })}</nav>
          <div className="mt-auto space-y-3 px-1"><HealthPanel health={health} reachable={healthReachable}/><div className="flex items-center gap-2 px-2 py-1"><div className="grid size-8 place-items-center rounded-lg border border-white/8 bg-white/5 text-[11px] font-bold text-cyan-200">{identity.display_name.slice(0,2).toUpperCase()}</div><div className="min-w-0 flex-1"><div className="truncate text-xs font-semibold">{identity.display_name}</div><div className="tm-label mt-1">{identity.role} · {identity.auth_type}</div></div><button onClick={() => void logout()} className="text-slate-600 hover:text-slate-300" title="Disconnect"><LogOut className="size-4"/></button></div></div>
        </aside>
        <section className="flex min-w-0 flex-1 flex-col p-1 sm:p-2">
          <header className="mb-2 flex h-12 items-center justify-between gap-3 px-2 sm:px-3">
            <div className="min-w-0"><div className="flex items-center gap-3"><span className="tm-label">{view === "chat" ? "copilot channel" : view === "overview" ? "command center" : `${view} console`}</span><span className="hidden h-3 w-px bg-white/8 sm:block"/><span className="hidden truncate text-[10px] text-slate-600 sm:block">{current.description}</span></div></div>
            <div className="flex shrink-0 items-center gap-2"><button onClick={() => { setCommandQuery(""); setCommandOpen(true); }} className="tm-control flex size-8 items-center justify-center rounded-lg md:hidden" aria-label="Open command launcher"><Command className="size-3.5 text-cyan-200"/></button><Badge className={cn("hidden sm:inline-flex", healthBadgeClass)}><Activity className="size-3"/><span className={`tm-led ${healthLedClass}`}/> core {healthState}</Badge><Badge className="text-emerald-300"><span className="tm-led"/> connected</Badge></div>
          </header>
          {view === "chat" ? <ChatWorkbench /> : view === "overview" ? <CommandCenter identity={identity}/> : <DataDeck view={view} identity={identity} />}
          <nav className="tm-mobile-nav mt-2 grid gap-1 px-1 md:hidden" style={{ gridTemplateColumns: `repeat(${permitted.length}, minmax(0, 1fr))` }}>{permitted.map((item) => { const Icon = item.icon; const active = pathname === item.href; return <Link key={item.view} href={item.href} className={cn("flex min-w-0 flex-col items-center justify-center gap-1 rounded-lg px-1 py-2 text-[8px] uppercase tracking-[.08em] text-slate-600", active && "is-active text-cyan-200")}><Icon className="size-3.5"/><span className="truncate">{item.label}</span></Link>; })}</nav>
        </section>
      </div>
      <CommandLauncher open={commandOpen} query={commandQuery} setQuery={setCommandQuery} items={permitted} activeView={view} health={health} healthReachable={healthReachable} identity={identity} onClose={() => setCommandOpen(false)} onNavigate={navigate}/>
    </main>
  );
}