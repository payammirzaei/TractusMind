"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { KeyRound, Plus, RefreshCw, ShieldCheck, Trash2, UserPlus, Users, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Identity, ManagedUser, UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, { cache: "no-store", ...init });
  if (response.status === 204) return undefined as T;
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? `Request failed: ${response.status}`);
  return payload as T;
}

export function AdminPasswordManager() {
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [me, records] = await Promise.all([
        request<Identity>("/v1/me"),
        request<ManagedUser[]>("/v1/ops/users"),
      ]);
      setIdentity(me);
      setUsers(records);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Account management unavailable");
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [load, open]);

  const localAccounts = useMemo(
    () => users.filter((user) => user.auth_type === "password"),
    [users],
  );

  async function createPasswordAccount() {
    if (!displayName.trim() || !username.trim() || password.length < 12) return;
    setBusy("create");
    setError(null);
    try {
      await request<ManagedUser>("/v1/ops/users/password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          display_name: displayName.trim(),
          username: username.trim(),
          password,
          role,
        }),
      });
      setDisplayName("");
      setUsername("");
      setPassword("");
      setRole("user");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Password account creation failed");
    } finally {
      setBusy(null);
    }
  }

  async function deleteAccount(user: ManagedUser) {
    const label = user.username ? `${user.display_name} (@${user.username})` : user.display_name;
    if (!window.confirm(`Delete ${label}? Historical conversations will be kept but detached from this account.`)) return;
    setBusy(user.user_id);
    setError(null);
    try {
      await request<void>(`/v1/ops/users/${user.user_id}`, { method: "DELETE" });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Account deletion failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Manage human accounts"
        className="tm-control flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-300/15 px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[.12em] text-cyan-100"
      >
        <UserPlus className="size-3.5 text-cyan-300"/>
        Human accounts
      </button>

      {open && (
        <div className="fixed inset-0 z-[120] bg-black/65 backdrop-blur-sm" onMouseDown={(event) => { if (event.currentTarget === event.target) setOpen(false); }}>
          <aside className="tm-shell tm-scrollbar absolute right-0 top-0 h-full w-full max-w-[520px] overflow-y-auto border-l border-white/8 p-3 sm:p-4">
            <div className="tm-well min-h-full rounded-2xl p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="tm-label">local identity control</div>
                  <h2 className="mt-1 text-xl font-semibold">Human accounts</h2>
                  <p className="mt-2 text-xs leading-5 text-slate-600">Create human Mission Control accounts with username/password login, or permanently remove identities.</p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setOpen(false)}><X className="size-4"/></Button>
              </div>

              {error && <div className="mt-4 rounded-xl border border-red-300/15 bg-red-300/5 p-3 text-xs text-red-200">{error}</div>}

              <div className="tm-inspector mt-5 rounded-2xl p-4">
                <div className="mb-4 flex items-center gap-2"><UserPlus className="size-4 text-cyan-300"/><span className="text-sm font-semibold">Create human account</span></div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label><span className="tm-label mb-2 block">display name</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="tm-field w-full rounded-xl px-3 py-2.5 text-sm outline-none" placeholder="Engineering user"/></label>
                  <label><span className="tm-label mb-2 block">username</span><input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" className="tm-field w-full rounded-xl px-3 py-2.5 font-mono text-sm outline-none" placeholder="username"/></label>
                </div>
                <label className="mt-3 block"><span className="tm-label mb-2 block">password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" className="tm-field w-full rounded-xl px-3 py-2.5 text-sm outline-none" placeholder="Minimum 12 characters"/></label>
                <div className="mt-3"><span className="tm-label mb-2 block">role</span><div className="grid grid-cols-3 gap-2">{(["user", "operator", "admin"] as UserRole[]).map((item) => <button key={item} type="button" onClick={() => setRole(item)} className={cn("tm-control rounded-lg px-2 py-2 text-[10px] uppercase tracking-wider", role === item ? "text-cyan-200" : "text-slate-500")}>{item}</button>)}</div></div>
                <Button variant="primary" className="mt-4 w-full" onClick={() => void createPasswordAccount()} disabled={busy === "create" || !displayName.trim() || !username.trim() || password.length < 12}><Plus className="size-4"/>{busy === "create" ? "Creating…" : "Create human account"}</Button>
                <div className="mt-2 text-[10px] text-slate-700">Password is hashed with scrypt by the backend and is never stored or returned in plaintext.</div>
              </div>

              <div className="mt-5 flex items-center justify-between">
                <div><div className="tm-label">human accounts</div><div className="mt-1 text-xs text-slate-600">{localAccounts.length} password identities · {users.length} total identities</div></div>
                <Button size="sm" onClick={() => void load()} disabled={busy !== null}><RefreshCw className="size-3.5"/>Refresh</Button>
              </div>

              <div className="mt-3 space-y-2">
                {users.map((user) => {
                  const current = identity?.user_id === user.user_id;
                  return (
                    <div key={user.user_id} className="tm-user-row flex items-center gap-3 rounded-xl p-3">
                      <div className="grid size-9 shrink-0 place-items-center rounded-lg border border-white/8 bg-black/20 text-[10px] font-bold text-cyan-200">{user.display_name.slice(0,2).toUpperCase()}</div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2"><span className="truncate text-sm font-semibold">{user.display_name}</span>{current && <Badge className="text-emerald-300">you</Badge>}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-2"><Badge>{user.auth_type}</Badge>{user.username && <span className="font-mono text-[9px] text-slate-500">@{user.username}</span>}<span className="text-[9px] uppercase tracking-wider text-slate-700">{user.role}</span></div>
                      </div>
                      <Button
                        size="sm"
                        disabled={current || busy === user.user_id}
                        onClick={() => void deleteAccount(user)}
                        className="text-red-300"
                        title={current ? "You cannot delete your current account" : "Delete account"}
                      >
                        <Trash2 className="size-3.5"/>{busy === user.user_id ? "Deleting…" : "Delete"}
                      </Button>
                    </div>
                  );
                })}
                {users.length === 0 && <div className="rounded-xl border border-dashed border-white/6 p-8 text-center text-xs text-slate-700"><Users className="mx-auto mb-3 size-5"/>No identities found.</div>}
              </div>

              <div className="mt-5 flex items-center gap-2 rounded-xl border border-amber-300/10 bg-amber-300/5 p-3 text-[10px] leading-5 text-amber-100/60"><ShieldCheck className="size-4 shrink-0 text-amber-300"/>The current account and the last enabled admin are protected from deletion.</div>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
