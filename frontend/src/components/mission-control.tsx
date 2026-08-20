"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  Bot,
  Database,
  Gauge,
  KeyRound,
  LogOut,
  SearchCode,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChatWorkbench } from "@/components/chat-workbench";
import { DataDeck } from "@/components/data-deck";
import type { Identity, UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

export type MissionView = "chat" | "sources" | "ops" | "quality" | "admin";

type HealthCheck = "ok" | "error";
type SystemHealth = {
  status: "ok" | "degraded";
  checks: {
    postgres: HealthCheck;
    redis: HealthCheck;
    qdrant: HealthCheck;
  };
};

const NAV: Array<{ view: MissionView; href: string; label: string; icon: typeof Bot; minimum: UserRole }> = [
  { view: "chat", href: "/", label: "Copilot", icon: Bot, minimum: "user" },
  { view: "sources", href: "/sources", label: "Sources", icon: Database, minimum: "operator" },
  { view: "ops", href: "/ops", label: "Operations", icon: Gauge, minimum: "operator" },
  { view: "quality", href: "/quality", label: "Quality", icon: ShieldCheck, minimum: "operator" },
  { view: "admin", href: "/admin", label: "Access", icon: Users, minimum: "admin" },
];

const roleRank: Record<UserRole, number> = { user: 0, operator: 1, admin: 2 };

function LoginConsole({ onReady }: { onReady: (identity: Identity) => void }) {
  const [token, setToken] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connect() {
    if (!token.trim()) return;
    setPending(true); setError(null);
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Credential rejected");
      setToken(""); onReady(payload as Identity);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication failed");
    } finally { setPending(false); }
  }

  return (
    <main className="grid min-h-screen place-items-center p-5">
      <motion.div initial={{ opacity: 0, scale: .98, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} className="tm-shell relative w-full max-w-[520px] rounded-[28px] p-3">
        <span className="tm-screw absolute left-4 top-4"/><span className="tm-screw absolute right-4 top-4"/><span className="tm-screw absolute bottom-4 left-4"/><span className="tm-screw absolute bottom-4 right-4"/>
        <div className="tm-well tm-scanline rounded-[20px] px-6 py-8 sm:px-9">
          <div className="mb-8 flex items-center gap-4">
            <div className="tm-control grid size-12 place-items-center rounded-2xl border-cyan-300/15"><Sparkles className="size-5 text-cyan-200"/></div>
            <div><div className="tm-label">TractusMind</div><h1 className="mt-1 text-xl font-semibold tracking-tight">Mission Control</h1></div>
          </div>
          <Badge className="mb-5 border-emerald-300/15 text-emerald-300"><span className="tm-led"/> secure console</Badge>
          <h2 className="text-3xl font-semibold tracking-[-.035em]">Engineering intelligence,<br/><span className="text-slate-500">with the panels open.</span></h2>
          <p className="mt-4 text-sm leading-6 text-slate-500">Connect with a TractusMind API key or an OIDC access token. The credential is stored only in an HttpOnly session cookie.</p>
          <div className="mt-8">
            <label className="tm-label mb-2 block">Bearer credential</label>
            <div className="tm-well flex items-center gap-2 rounded-xl p-2">
              <KeyRound className="ml-2 size-4 text-slate-600"/>
              <input type="password" value={token} onChange={(event) => setToken(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void connect(); }} placeholder="tm_... or enterprise JWT" autoComplete="off" className="min-w-0 flex-1 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-slate-700"/>
              <Button variant="primary" onClick={() => void connect()} disabled={pending || !token.trim()}>{pending ? "Verifying…" : "Connect"}</Button>
            </div>
            {error && <div className="mt-3 rounded-lg border border-red-300/15 bg-red-300/5 p-3 text-xs text-red-200">{error}</div>}
          </div>
          <div className="mt-8 flex items-center justify-between border-t border-white/5 pt-4 text-[10px] uppercase tracking-[.14em] text-slate-700"><span>OIDC / API key</span><span>RBAC aware</span><span>HttpOnly session</span></div>
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
  const checks: Array<[keyof SystemHealth["checks"], string]> = [
    ["postgres", "Postgres"],
    ["redis", "Redis"],
    ["qdrant", "Qdrant"],
  ];

  return (
    <div className="tm-well rounded-xl p-3" aria-live="polite">
      <div className="flex items-center gap-2"><span className={`tm-led ${led}`}/><span className="tm-label">Core {state}</span></div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-slate-600">
        {checks.map(([key, label]) => {
          const check = health?.checks[key];
          return (
            <div key={key} className="contents">
              <span>{label}</span>
              <span className={cn("text-right", check === "ok" ? "text-emerald-300" : check === "error" ? "text-red-300" : "text-slate-500")}>{check ?? "—"}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function MissionControl({ view }: { view: MissionView }) {
  const pathname = usePathname();
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [healthReachable, setHealthReachable] = useState(true);

  useEffect(() => {
    fetch("/api/session", { cache: "no-store" })
      .then(async (response) => response.ok ? setIdentity(await response.json()) : setIdentity(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch("/api/backend/health/ready", { cache: "no-store" });
        const payload = await response.json();
        const valid = payload && typeof payload === "object" && "status" in payload && "checks" in payload;
        if (cancelled) return;
        if (valid) {
          setHealth(payload as SystemHealth);
          setHealthReachable(true);
        } else {
          setHealth(null);
          setHealthReachable(false);
        }
      } catch {
        if (!cancelled) {
          setHealth(null);
          setHealthReachable(false);
        }
      }
    }

    void loadHealth();
    const timer = window.setInterval(() => void loadHealth(), 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  async function logout() {
    await fetch("/api/session", { method: "DELETE" });
    setIdentity(null);
  }

  if (loading) return <BootPanel />;
  if (!identity) return <LoginConsole onReady={setIdentity} />;

  const permitted = NAV.filter((item) => roleRank[identity.role] >= roleRank[item.minimum]);
  if (!permitted.some((item) => item.view === view)) {
    return <main className="grid min-h-screen place-items-center"><div className="tm-panel rounded-2xl p-8 text-center"><ShieldCheck className="mx-auto mb-3 size-6 text-amber-300"/><h1 className="font-semibold">Insufficient role</h1><p className="mt-2 text-sm text-slate-500">This console requires elevated TractusMind access.</p><Link href="/"><Button className="mt-5">Back to copilot</Button></Link></div></main>;
  }

  const healthState = !healthReachable ? "offline" : health?.status ?? "checking";
  const healthBadgeClass = healthState === "ok" ? "text-emerald-300" : healthState === "degraded" ? "text-amber-300" : healthState === "offline" ? "text-red-300" : "text-cyan-300";
  const healthLedClass = healthState === "degraded" ? "amber" : healthState === "offline" ? "red" : healthState === "checking" ? "cyan" : "";

  return (
    <main className="h-screen overflow-hidden p-2 sm:p-3">
      <div className="tm-shell relative flex h-full overflow-hidden rounded-[24px] p-2">
        <span className="tm-screw absolute left-2 top-2"/><span className="tm-screw absolute right-2 top-2"/><span className="tm-screw absolute bottom-2 left-2"/><span className="tm-screw absolute bottom-2 right-2"/>
        <aside className="tm-desktop-only flex w-[210px] shrink-0 flex-col px-2 py-3">
          <div className="mb-7 flex items-center gap-3 px-2">
            <div className="tm-control grid size-10 place-items-center rounded-xl"><SearchCode className="size-4 text-cyan-200"/></div>
            <div><div className="text-sm font-bold tracking-tight">TractusMind</div><div className="tm-label mt-1">Mission Control</div></div>
          </div>
          <nav className="space-y-1">
            {permitted.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return <Link key={item.view} href={item.href} className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs font-semibold text-slate-500 transition", active ? "tm-well text-cyan-200" : "hover:bg-white/[.03] hover:text-slate-200")}><Icon className="size-4"/><span>{item.label}</span>{active && <span className="ml-auto tm-led cyan"/>}</Link>;
            })}
          </nav>
          <div className="mt-auto space-y-3 px-1">
            <HealthPanel health={health} reachable={healthReachable}/>
            <div className="flex items-center gap-2 px-2 py-1">
              <div className="grid size-8 place-items-center rounded-lg border border-white/8 bg-white/5 text-[11px] font-bold text-cyan-200">{identity.display_name.slice(0,2).toUpperCase()}</div>
              <div className="min-w-0 flex-1"><div className="truncate text-xs font-semibold">{identity.display_name}</div><div className="tm-label mt-1">{identity.role} · {identity.auth_type}</div></div>
              <button onClick={() => void logout()} className="text-slate-600 hover:text-slate-300" title="Disconnect"><LogOut className="size-4"/></button>
            </div>
          </div>
        </aside>
        <section className="flex min-w-0 flex-1 flex-col p-1 sm:p-2">
          <header className="mb-2 flex h-11 items-center justify-between px-2 sm:px-3">
            <div className="flex items-center gap-3"><span className="tm-label">{view === "chat" ? "copilot channel" : `${view} console`}</span><span className="hidden h-3 w-px bg-white/8 sm:block"/><span className="hidden text-[10px] text-slate-600 sm:block">source-grounded · version-aware · inspectable</span></div>
            <div className="flex items-center gap-2"><Badge className={cn("hidden sm:inline-flex", healthBadgeClass)}><Activity className="size-3"/><span className={`tm-led ${healthLedClass}`}/> core {healthState}</Badge><Badge className="text-emerald-300"><span className="tm-led"/> connected</Badge></div>
          </header>
          {view === "chat" ? <ChatWorkbench /> : <DataDeck view={view} identity={identity} />}
          <nav className="mt-2 flex gap-1 overflow-x-auto px-1 md:hidden">
            {permitted.map((item) => { const Icon = item.icon; return <Link key={item.view} href={item.href} className={cn("tm-control flex h-9 min-w-10 items-center justify-center gap-1 rounded-lg px-3 text-[10px]", pathname === item.href && "text-cyan-200")}><Icon className="size-3.5"/><span>{item.label}</span></Link>; })}
          </nav>
        </section>
      </div>
    </main>
  );
}
