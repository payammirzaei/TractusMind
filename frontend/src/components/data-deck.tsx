"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  AlertTriangle,
  Database,
  FileCode2,
  KeyRound,
  Play,
  Plus,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  UserRoundCog,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Identity, ManagedUser, OpsSummary, QualityReview, RunStatus, SourceStatus, UserRole } from "@/lib/types";
import { formatDate, shortSha } from "@/lib/utils";
import type { MissionView } from "@/components/mission-control";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, { cache: "no-store", ...init });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? `Request failed: ${response.status}`);
  return payload as T;
}

function Stat({ label, value, tone = "cyan" }: { label: string; value: string | number; tone?: "cyan" | "green" | "amber" | "red" }) {
  const color = { cyan: "text-cyan-200", green: "text-emerald-300", amber: "text-amber-300", red: "text-red-300" }[tone];
  return <div className="tm-panel rounded-xl p-4"><div className="tm-label">{label}</div><div className={`mt-3 text-2xl font-semibold tracking-tight ${color}`}>{value}</div></div>;
}

function DeckHeader({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return <div className="mb-4 flex items-end justify-between"><div><div className="tm-label">{eyebrow}</div><h1 className="mt-1 text-xl font-semibold tracking-tight">{title}</h1></div>{action}</div>;
}

function LoadingDeck() {
  return <div className="tm-panel grid min-h-0 flex-1 place-items-center rounded-2xl"><div className="flex items-center gap-3"><RefreshCw className="size-4 animate-spin text-cyan-300"/><span className="tm-label">reading control plane</span></div></div>;
}

function SourceDeck({ identity }: { identity: Identity }) {
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => json<SourceStatus[]>("/v1/ops/sources").then(setSources).catch((e) => setError(e.message)).finally(() => setLoading(false)), []);
  useEffect(() => { void load(); }, [load]);
  async function sync(sourceId: string) {
    setBusy(sourceId); setError(null);
    try { await json(`/v1/ops/sources/${sourceId}/sync`, { method: "POST" }); await load(); } catch (e) { setError(e instanceof Error ? e.message : "Sync failed"); } finally { setBusy(null); }
  }
  if (loading) return <LoadingDeck />;
  return <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
    <DeckHeader eyebrow="knowledge plane" title="Versioned source registry" action={<Badge className="text-cyan-300"><Database className="size-3"/>{sources.length} sources</Badge>}/>
    {error && <div className="mb-3 rounded-xl border border-red-300/15 bg-red-300/5 p-3 text-xs text-red-200">{error}</div>}
    <div className="grid gap-3 xl:grid-cols-2">
      {sources.map((source) => <motion.div layout key={source.source_id} className="tm-well rounded-2xl p-4">
        <div className="flex items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className={`tm-led ${source.latest_run_status === "failed" ? "red" : source.locked ? "amber" : ""}`}/><span className="text-sm font-semibold">{source.component}</span></div><div className="mt-2 font-mono text-[11px] text-slate-600">{source.repository}</div></div><Badge>{source.priority}</Badge></div>
        <div className="mt-5 grid grid-cols-3 gap-2"><div className="tm-panel rounded-lg p-3"><div className="tm-label">files</div><div className="mt-2 font-mono text-sm text-slate-200">{source.file_count}</div></div><div className="tm-panel rounded-lg p-3"><div className="tm-label">snapshot</div><div className="mt-2 font-mono text-sm text-cyan-200">{shortSha(source.snapshot_commit_sha)}</div></div><div className="tm-panel rounded-lg p-3"><div className="tm-label">ref</div><div className="mt-2 truncate font-mono text-sm text-amber-200">{source.version_ref ?? source.configured_ref}</div></div></div>
        <div className="mt-4 flex items-center justify-between border-t border-white/5 pt-3"><div className="text-[10px] text-slate-600">Updated {formatDate(source.updated_at)} · {source.latest_run_status ?? "no run"}</div>{identity.role === "admin" && <Button size="sm" onClick={() => void sync(source.source_id)} disabled={busy === source.source_id || source.locked}><RefreshCw className={`size-3.5 ${busy === source.source_id ? "animate-spin" : ""}`}/> Sync</Button>}</div>
      </motion.div>)}
    </div>
  </div>;
}

function OpsDeck() {
  const [summary, setSummary] = useState<OpsSummary | null>(null);
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { try { const [s, r] = await Promise.all([json<OpsSummary>("/v1/ops/summary"), json<RunStatus[]>("/v1/ops/runs?limit=30")]); setSummary(s); setRuns(r); } catch (e) { setError(e instanceof Error ? e.message : "Ops unavailable"); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  if (loading) return <LoadingDeck />;
  return <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
    <DeckHeader eyebrow="runtime plane" title="Operations telemetry" action={<Button size="sm" onClick={() => void load()}><RefreshCw className="size-3.5"/>Refresh</Button>}/>
    {error && <div className="mb-3 text-xs text-red-300">{error}</div>}
    {summary && <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat label="indexed sources" value={`${summary.indexed_sources}/${summary.enabled_sources}`} tone="green"/><Stat label="running syncs" value={summary.running_sources}/><Stat label="failed sources" value={summary.failed_sources} tone={summary.failed_sources ? "red" : "green"}/><Stat label="redis" value={summary.redis_ok ? "ONLINE" : "DOWN"} tone={summary.redis_ok ? "green" : "red"}/></div>}
    <div className="mt-5 tm-well rounded-2xl p-3"><div className="mb-3 flex items-center gap-2 px-1"><ServerCog className="size-4 text-cyan-300"/><span className="text-sm font-semibold">Ingestion run channel</span></div><div className="space-y-1.5">{runs.map((run) => <div key={run.run_id} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl border border-white/[.035] bg-white/[.018] px-3 py-2.5"><span className={`tm-led ${run.status === "failed" ? "red" : run.status === "running" ? "amber" : ""}`}/><div className="min-w-0"><div className="flex gap-2"><span className="truncate text-xs font-semibold">{run.source_id}</span><span className="tm-mono text-[10px] text-slate-700">{shortSha(run.run_id)}</span></div><div className="mt-1 text-[10px] text-slate-600">{run.indexed_count} indexed · {run.chunk_count} chunks · +{run.added_count} ~{run.modified_count} -{run.deleted_count}</div></div><div className="text-right"><Badge className={run.status === "failed" ? "text-red-300" : run.status === "running" ? "text-amber-300" : "text-emerald-300"}>{run.status}</Badge><div className="mt-1 text-[9px] text-slate-700">{formatDate(run.started_at)}</div></div></div>)}</div></div>
  </div>;
}

function QualityDeck() {
  const [reviews, setReviews] = useState<QualityReview[]>([]);
  const [summary, setSummary] = useState<{ review_counts: Record<string, number>; regression_cases: number } | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { Promise.all([json<{ review_counts: Record<string, number>; regression_cases: number }>("/v1/ops/quality/summary"), json<QualityReview[]>("/v1/ops/quality/reviews?limit=50")]).then(([s, r]) => { setSummary(s); setReviews(r); }).finally(() => setLoading(false)); }, []);
  if (loading) return <LoadingDeck />;
  return <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
    <DeckHeader eyebrow="trust plane" title="Human-reviewed quality loop" action={<Badge className="text-emerald-300"><ShieldCheck className="size-3"/> regression guarded</Badge>}/>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat label="pending" value={summary?.review_counts.pending ?? 0} tone="amber"/><Stat label="promoted" value={summary?.review_counts.promoted ?? 0} tone="green"/><Stat label="dismissed" value={summary?.review_counts.dismissed ?? 0}/><Stat label="regressions" value={summary?.regression_cases ?? 0} tone="cyan"/></div>
    <div className="mt-5 grid gap-3 xl:grid-cols-2">{reviews.map((review) => <div key={review.review_id} className="tm-well rounded-2xl p-4"><div className="flex items-center justify-between"><div className="flex items-center gap-2">{review.error_type ? <AlertTriangle className="size-4 text-red-300"/> : <Activity className="size-4 text-amber-300"/>}<span className="tm-label">{review.trigger}</span></div><Badge className={review.status === "pending" ? "text-amber-300" : review.status === "promoted" ? "text-emerald-300" : ""}>{review.status}</Badge></div><div className="mt-4 text-sm font-semibold leading-6 text-slate-200">{review.question}</div>{review.answer && <div className="mt-3 line-clamp-3 text-xs leading-5 text-slate-500">{review.answer}</div>}<div className="mt-4 flex flex-wrap gap-2 border-t border-white/5 pt-3">{review.intent && <Badge>{review.intent}</Badge>}{review.feedback_rating && <Badge className={review.feedback_rating === "down" ? "text-red-300" : "text-emerald-300"}>feedback {review.feedback_rating}</Badge>}{review.root_cause && <Badge>{review.root_cause}</Badge>}<span className="ml-auto text-[9px] text-slate-700">{formatDate(review.created_at)}</span></div></div>)}</div>
  </div>;
}

function AdminDeck() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [credential, setCredential] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => json<ManagedUser[]>("/v1/ops/users").then(setUsers).finally(() => setLoading(false)), []);
  useEffect(() => { void load(); }, [load]);
  async function createUser() { if (!name.trim()) return; const created = await json<ManagedUser & { api_key: string }>("/v1/ops/users", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ display_name: name, role }) }); setCredential(created.api_key); setName(""); await load(); }
  async function toggle(user: ManagedUser) { await json(`/v1/ops/users/${user.user_id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ enabled: !user.enabled }) }); await load(); }
  if (loading) return <LoadingDeck />;
  return <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
    <DeckHeader eyebrow="identity plane" title="Users, roles & credentials" action={<Badge className="text-cyan-300"><UserRoundCog className="size-3"/>{users.length} identities</Badge>}/>
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <div className="tm-well rounded-2xl p-3"><div className="space-y-2">{users.map((user) => <div key={user.user_id} className="tm-panel flex items-center gap-3 rounded-xl p-3"><div className="grid size-9 place-items-center rounded-lg border border-white/8 bg-black/20 text-xs font-bold text-cyan-200">{user.display_name.slice(0,2).toUpperCase()}</div><div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{user.display_name}</div><div className="mt-1 flex gap-2"><Badge>{user.role}</Badge><Badge>{user.auth_type}</Badge>{user.api_key_prefix && <span className="tm-mono text-[9px] text-slate-700">{user.api_key_prefix}…</span>}</div></div><button onClick={() => void toggle(user)} className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500"><span className={`tm-led ${user.enabled ? "" : "red"}`}/>{user.enabled ? "enabled" : "disabled"}</button></div>)}</div></div>
      <div className="tm-well h-fit rounded-2xl p-4"><div className="mb-4 flex items-center gap-2"><Plus className="size-4 text-cyan-300"/><span className="text-sm font-semibold">Provision API identity</span></div><label className="tm-label">display name</label><input value={name} onChange={(e) => setName(e.target.value)} className="tm-panel mt-2 w-full rounded-xl px-3 py-2.5 text-sm outline-none focus:border-cyan-300/20" placeholder="Engineering operator"/><label className="tm-label mt-4 block">role</label><div className="mt-2 grid grid-cols-3 gap-2">{(["user","operator","admin"] as UserRole[]).map((item) => <button key={item} onClick={() => setRole(item)} className={`tm-control rounded-lg px-2 py-2 text-[10px] uppercase tracking-wider ${role === item ? "text-cyan-200" : "text-slate-500"}`}>{item}</button>)}</div><Button variant="primary" className="mt-4 w-full" onClick={() => void createUser()} disabled={!name.trim()}><KeyRound className="size-4"/>Create identity</Button>{credential && <div className="mt-4 rounded-xl border border-amber-300/15 bg-amber-300/5 p-3"><div className="tm-label text-amber-300">shown once</div><div className="mt-2 break-all font-mono text-[10px] leading-5 text-amber-100">{credential}</div></div>}</div>
    </div>
  </div>;
}

export function DataDeck({ view, identity }: { view: Exclude<MissionView, "chat">; identity: Identity }) {
  if (view === "sources") return <SourceDeck identity={identity}/>;
  if (view === "ops") return <OpsDeck/>;
  if (view === "quality") return <QualityDeck/>;
  return <AdminDeck/>;
}
