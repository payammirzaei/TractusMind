"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Copy, KeyRound, Plus, RotateCw, Search, ShieldCheck, UserRoundCog, Users, X } from "lucide-react";
import { motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Identity, ManagedUser, UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, { cache: "no-store", ...init });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? `Request failed: ${response.status}`);
  return payload as T;
}

function StatusDot({ enabled }: { enabled: boolean }) {
  return <span className={cn("tm-led", !enabled && "red")} />;
}

export function AccessDeck({ identity }: { identity: Identity }) {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [credential, setCredential] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setUsers(await json<ManagedUser[]>("/v1/ops/users"));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Access control unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function patchUser(user: ManagedUser, body: Record<string, unknown>) {
    setBusy(user.user_id); setError(null);
    try {
      await json(`/v1/ops/users/${user.user_id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Identity update failed");
    } finally {
      setBusy(null);
    }
  }

  async function createApiIdentity() {
    if (!name.trim()) return;
    setBusy("create"); setError(null);
    try {
      const created = await json<ManagedUser & { api_key: string }>("/v1/ops/users", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ display_name: name, role }),
      });
      setCredential(created.api_key);
      setCopied(false);
      setName("");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "API identity provisioning failed");
    } finally {
      setBusy(null);
    }
  }

  async function rotateApiKey(user: ManagedUser) {
    setBusy(user.user_id); setError(null);
    try {
      const updated = await json<ManagedUser & { api_key: string }>(
        `/v1/ops/users/${user.user_id}/rotate`,
        { method: "POST" },
      );
      setCredential(updated.api_key);
      setCopied(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "API key rotation failed");
    } finally {
      setBusy(null);
    }
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return users.filter((user) => !needle || [
      user.display_name,
      user.username ?? "",
      user.role,
      user.auth_type,
      user.api_key_prefix ?? "",
    ].some((value) => value.toLowerCase().includes(needle)));
  }, [query, users]);

  const localCount = users.filter((user) => user.auth_type === "password").length;
  const apiCount = users.filter((user) => user.auth_type === "api_key").length;
  const oidcCount = users.filter((user) => user.auth_type === "oidc").length;

  if (loading) {
    return <div className="tm-panel grid min-h-0 flex-1 place-items-center rounded-2xl"><div className="tm-label">reading identity plane</div></div>;
  }

  return (
    <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="tm-label">identity plane</div>
          <h1 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">Human accounts & API identities</h1>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-600">Password accounts are for Mission Control users. API keys are reserved for machine clients. OIDC identities remain governed by the external identity provider.</p>
        </div>
        <Badge className="text-cyan-300"><UserRoundCog className="size-3"/>{users.length} identities</Badge>
      </div>

      {error && <div className="mb-4 rounded-xl border border-red-300/15 bg-red-300/5 p-3 text-xs text-red-200">{error}</div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="tm-stat tm-panel rounded-xl p-4"><div className="tm-label">local accounts</div><div className="mt-3 text-2xl font-semibold text-emerald-300">{localCount}</div></div>
        <div className="tm-stat tm-panel rounded-xl p-4"><div className="tm-label">API identities</div><div className="mt-3 text-2xl font-semibold text-cyan-200">{apiCount}</div></div>
        <div className="tm-stat tm-panel rounded-xl p-4"><div className="tm-label">external OIDC</div><div className="mt-3 text-2xl font-semibold text-amber-300">{oidcCount}</div></div>
        <div className="tm-stat tm-panel rounded-xl p-4"><div className="tm-label">your session</div><div className="mt-3 text-sm font-semibold text-slate-200">{identity.username ?? identity.display_name}</div><div className="mt-1 text-[10px] text-slate-600">{identity.role} · {identity.auth_type}</div></div>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <label className="tm-search mb-3 flex h-10 items-center gap-2 rounded-xl px-3">
            <Search className="size-3.5 text-slate-600"/>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, username, role, auth type…" className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-700"/>
            {query && <button onClick={() => setQuery("")} className="text-slate-700 hover:text-slate-400"><X className="size-3.5"/></button>}
          </label>

          <div className="tm-well rounded-2xl p-3">
            <div className="space-y-2">
              {filtered.map((user) => {
                const external = user.auth_type === "oidc";
                const machine = user.auth_type === "api_key";
                return (
                  <div key={user.user_id} className="tm-user-row flex flex-wrap items-center gap-3 rounded-xl p-3">
                    <div className="grid size-10 place-items-center rounded-xl border border-white/8 bg-black/20 text-xs font-bold text-cyan-200">{user.display_name.slice(0, 2).toUpperCase()}</div>
                    <div className="min-w-[180px] flex-1">
                      <div className="truncate text-sm font-semibold">{user.display_name}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        <Badge>{user.auth_type}</Badge>
                        {user.username && <span className="font-mono text-[9px] text-slate-500">@{user.username}</span>}
                        {user.api_key_prefix && <span className="font-mono text-[9px] text-slate-700">{user.api_key_prefix}…</span>}
                      </div>
                    </div>
                    {external ? (
                      <Badge className="text-amber-300"><ShieldCheck className="size-3"/>{user.role} · IdP</Badge>
                    ) : (
                      <select value={user.role} disabled={busy === user.user_id} onChange={(event) => void patchUser(user, { role: event.target.value })} className="tm-field h-8 rounded-lg px-2 text-[10px] uppercase tracking-wider outline-none">
                        <option value="user">user</option><option value="operator">operator</option><option value="admin">admin</option>
                      </select>
                    )}
                    {machine && <Button size="sm" onClick={() => void rotateApiKey(user)} disabled={busy === user.user_id}><RotateCw className={cn("size-3.5", busy === user.user_id && "animate-spin")}/>Rotate API key</Button>}
                    <button disabled={busy === user.user_id} onClick={() => void patchUser(user, { enabled: !user.enabled })} className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500 disabled:opacity-40"><StatusDot enabled={user.enabled}/>{user.enabled ? "enabled" : "disabled"}</button>
                  </div>
                );
              })}
              {filtered.length === 0 && <div className="p-8 text-center text-xs text-slate-700"><Users className="mx-auto mb-3 size-5"/>No identities match.</div>}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="tm-inspector rounded-2xl p-4">
            <div className="mb-4 flex items-center gap-2"><Plus className="size-4 text-cyan-300"/><span className="text-sm font-semibold">Provision machine identity</span></div>
            <p className="mb-4 text-[10px] leading-5 text-slate-600">Creates an API key for automation or service-to-service access. Human login credentials are managed separately.</p>
            <label className="tm-label">display name</label>
            <input value={name} onChange={(event) => setName(event.target.value)} className="tm-field mt-2 w-full rounded-xl px-3 py-2.5 text-sm outline-none" placeholder="Automation client"/>
            <label className="tm-label mt-4 block">role</label>
            <div className="mt-2 grid grid-cols-3 gap-2">{(["user", "operator", "admin"] as UserRole[]).map((item) => <button key={item} onClick={() => setRole(item)} className={cn("tm-control rounded-lg px-2 py-2 text-[10px] uppercase tracking-wider", role === item ? "text-cyan-200" : "text-slate-500")}>{item}</button>)}</div>
            <Button variant="primary" className="mt-4 w-full" onClick={() => void createApiIdentity()} disabled={!name.trim() || busy === "create"}><KeyRound className="size-4"/>{busy === "create" ? "Provisioning…" : "Create API identity"}</Button>
          </div>

          {credential && <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-amber-300/15 bg-amber-300/5 p-4"><div className="flex items-center justify-between"><div><div className="tm-label text-amber-300">one-time API credential</div><div className="mt-1 text-xs text-amber-100/70">Copy it now. It will not be shown again.</div></div><button onClick={() => setCredential(null)} className="text-amber-200/50 hover:text-amber-200"><X className="size-4"/></button></div><div className="mt-3 break-all rounded-xl bg-black/25 p-3 font-mono text-[10px] leading-5 text-amber-100">{credential}</div><Button className="mt-3 w-full" onClick={async () => { await navigator.clipboard.writeText(credential); setCopied(true); window.setTimeout(() => setCopied(false), 1200); }}>{copied ? <Check className="size-3.5 text-emerald-300"/> : <Copy className="size-3.5"/>}{copied ? "Copied" : "Copy API key"}</Button></motion.div>}
        </div>
      </div>
    </div>
  );
}
