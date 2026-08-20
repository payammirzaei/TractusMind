"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  ArrowRight,
  Database,
  GitBranch,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  UserRoundCog,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Identity, OpsSummary, QualityReview, RunStatus, SourceStatus } from "@/lib/types";
import { cn, formatDate, shortSha } from "@/lib/utils";

type HealthCheck = "ok" | "error";
type SystemHealth = {
  status: "ok" | "degraded";
  checks: {
    postgres: HealthCheck;
    redis: HealthCheck;
    qdrant: HealthCheck;
  };
};

type QualitySummary = {
  review_counts: Record<string, number>;
  regression_cases: number;
};

type CommandSnapshot = {
  health: SystemHealth | null;
  summary: OpsSummary | null;
  sources: SourceStatus[];
  runs: RunStatus[];
  quality: QualitySummary | null;
  reviews: QualityReview[];
};

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, { cache: "no-store", ...init });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? `Request failed: ${response.status}`);
  return payload as T;
}

async function readHealth(): Promise<SystemHealth | null> {
  try {
    const response = await fetch("/api/backend/health/ready", { cache: "no-store" });
    const payload = await response.json();
    const valid = payload && typeof payload === "object" && (payload.status === "ok" || payload.status === "degraded") && payload.checks;
    return valid ? payload as SystemHealth : null;
  } catch {
    return null;
  }
}

function Metric({ label, value, detail, tone = "cyan" }: { label: string; value: string | number; detail: string; tone?: "cyan" | "green" | "amber" | "red" }) {
  const color = { cyan: "text-cyan-200", green: "text-emerald-300", amber: "text-amber-300", red: "text-red-300" }[tone];
  return (
    <div className="tm-stat tm-panel rounded-2xl p-4">
      <div className="tm-label">{label}</div>
      <div className={cn("mt-3 text-2xl font-semibold tracking-tight", color)}>{value}</div>
      <div className="mt-2 text-[10px] leading-4 text-slate-600">{detail}</div>
    </div>
  );
}

function DependencyNode({ label, state }: { label: string; state?: HealthCheck }) {
  return (
    <div className="tm-command-node rounded-xl p-3">
      <div className="flex items-center gap-2">
        <span className={cn("tm-led", state === "error" && "red", state == null && "cyan")}/>
        <span className="text-xs font-semibold text-slate-300">{label}</span>
      </div>
      <div className={cn("mt-2 font-mono text-[9px] uppercase tracking-[.12em]", state === "ok" ? "text-emerald-300" : state === "error" ? "text-red-300" : "text-slate-600")}>{state ?? "unknown"}</div>
    </div>
  );
}

export function CommandCenter({ identity }: { identity: Identity }) {
  const [snapshot, setSnapshot] = useState<CommandSnapshot>({ health: null, summary: null, sources: [], runs: [], quality: null, reviews: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const [health, summary, sources, runs, quality, reviews] = await Promise.all([
        readHealth(),
        json<OpsSummary>("/v1/ops/summary"),
        json<SourceStatus[]>("/v1/ops/sources"),
        json<RunStatus[]>("/v1/ops/runs?limit=24"),
        json<QualitySummary>("/v1/ops/quality/summary"),
        json<QualityReview[]>("/v1/ops/quality/reviews?limit=8"),
      ]);
      setSnapshot({ health, summary, sources, runs, quality, reviews });
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Command Center unavailable");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
    const timer = window.setInterval(() => void load(true), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function syncAll() {
    setSyncing(true); setError(null);
    try {
      await json("/v1/ops/sync", { method: "POST" });
      await load(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to enqueue source synchronization");
    } finally {
      setSyncing(false);
    }
  }

  const indexed = snapshot.sources.filter((source) => Boolean(source.snapshot_commit_sha)).length;
  const enabled = snapshot.sources.filter((source) => source.enabled).length;
  const failedSources = snapshot.sources.filter((source) => source.latest_run_status === "failed").length;
  const runningSources = snapshot.sources.filter((source) => source.latest_run_status === "running" || source.locked).length;
  const pendingReviews = snapshot.quality?.review_counts.pending ?? 0;
  const regressions = snapshot.quality?.regression_cases ?? 0;
  const promoted = snapshot.quality?.review_counts.promoted ?? 0;
  const healthOk = snapshot.health?.status === "ok";
  const missionTone = !snapshot.health ? "cyan" : !healthOk || failedSources > 0 ? "red" : pendingReviews > 0 ? "amber" : "green";
  const missionLabel = !snapshot.health ? "Health telemetry unavailable" : !healthOk ? "Core degraded" : failedSources > 0 ? "Source attention required" : pendingReviews > 0 ? "Quality review pending" : "Mission nominal";

  const activityMax = Math.max(1, ...snapshot.runs.slice(0, 12).map((run) => Math.max(run.indexed_count, run.chunk_count)));
  const recentRuns = useMemo(() => snapshot.runs.slice(0, 12).reverse(), [snapshot.runs]);

  if (loading) {
    return <div className="tm-panel grid min-h-0 flex-1 place-items-center rounded-2xl"><div className="flex items-center gap-3"><RefreshCw className="size-4 animate-spin text-cyan-300"/><span className="tm-label">assembling command telemetry</span></div></div>;
  }

  return (
    <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="tm-label">mission plane</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-[-.03em]">Command Center</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2"><Badge className={missionTone === "green" ? "text-emerald-300" : missionTone === "amber" ? "text-amber-300" : missionTone === "red" ? "text-red-300" : "text-cyan-300"}><span className={cn("tm-led", missionTone === "amber" && "amber", missionTone === "red" && "red", missionTone === "cyan" && "cyan")}/>{missionLabel}</Badge><span className="text-[10px] text-slate-600">live control-plane snapshot · refreshes every 15s</span></div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => void load()} disabled={refreshing}><RefreshCw className={cn("size-3.5", refreshing && "animate-spin")}/>Refresh</Button>
          {identity.role === "admin" && <Button size="sm" variant="primary" onClick={() => void syncAll()} disabled={syncing}><GitBranch className="size-3.5"/>{syncing ? "Queueing…" : "Sync all sources"}</Button>}
        </div>
      </div>

      {error && <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} className="mt-4 rounded-xl border border-red-300/15 bg-red-300/5 p-3 text-xs text-red-200">{error}</motion.div>}

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label="core" value={snapshot.health?.status?.toUpperCase() ?? "UNKNOWN"} detail="Postgres · Redis · Qdrant readiness" tone={healthOk ? "green" : snapshot.health ? "red" : "cyan"}/>
        <Metric label="source coverage" value={`${indexed}/${enabled}`} detail={`${failedSources} failed · ${runningSources} active`} tone={enabled === 0 ? "cyan" : indexed === enabled && failedSources === 0 ? "green" : failedSources > 0 ? "red" : "amber"}/>
        <Metric label="sync activity" value={snapshot.summary?.running_sources ?? runningSources} detail={`${snapshot.runs.length} recent runs loaded`} tone={runningSources > 0 ? "cyan" : "green"}/>
        <Metric label="quality inbox" value={pendingReviews} detail={`${promoted} promoted reviews`} tone={pendingReviews > 0 ? "amber" : "green"}/>
        <Metric label="regression guard" value={regressions} detail="human-reviewed production cases" tone="cyan"/>
      </div>

      <div className="mt-5 grid gap-4 2xl:grid-cols-[1.08fr_.92fr]">
        <section className="tm-command-map rounded-2xl p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3"><div><div className="tm-label">live topology</div><h2 className="mt-1 text-base font-semibold">Grounded answer control path</h2></div><Badge className="text-cyan-300"><Activity className="size-3"/>readiness wired</Badge></div>
          <div className="mt-6 grid items-center gap-3 md:grid-cols-[1fr_auto_1fr_auto_1.2fr]">
            <div className="tm-command-node rounded-xl p-4"><div className="flex items-center gap-2"><span className="tm-led cyan"/><span className="text-xs font-semibold">Mission Control</span></div><div className="mt-2 text-[10px] text-slate-600">BFF · secure session · RBAC</div></div>
            <ArrowRight className="mx-auto size-4 rotate-90 text-slate-700 md:rotate-0"/>
            <div className="tm-command-node rounded-xl p-4"><div className="flex items-center gap-2"><span className={cn("tm-led", snapshot.health?.status === "degraded" && "amber", !snapshot.health && "cyan")}/><span className="text-xs font-semibold">FastAPI Core</span></div><div className="mt-2 text-[10px] text-slate-600">route · retrieve · rerank · verify</div></div>
            <ArrowRight className="mx-auto size-4 rotate-90 text-slate-700 md:rotate-0"/>
            <div className="grid grid-cols-3 gap-2"><DependencyNode label="Postgres" state={snapshot.health?.checks.postgres}/><DependencyNode label="Redis" state={snapshot.health?.checks.redis}/><DependencyNode label="Qdrant" state={snapshot.health?.checks.qdrant}/></div>
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-3">
            <Link href="/sources" className="tm-command-link rounded-xl p-3"><Database className="size-4 text-cyan-300"/><div className="mt-3 text-xs font-semibold">Knowledge plane</div><div className="mt-1 text-[10px] text-slate-600">{indexed} indexed source snapshots</div></Link>
            <Link href="/ops" className="tm-command-link rounded-xl p-3"><ServerCog className="size-4 text-cyan-300"/><div className="mt-3 text-xs font-semibold">Runtime plane</div><div className="mt-1 text-[10px] text-slate-600">{runningSources} syncs active now</div></Link>
            <Link href="/quality" className="tm-command-link rounded-xl p-3"><ShieldCheck className="size-4 text-cyan-300"/><div className="mt-3 text-xs font-semibold">Trust plane</div><div className="mt-1 text-[10px] text-slate-600">{pendingReviews} reviews need attention</div></Link>
          </div>
        </section>

        <section className="tm-command-map rounded-2xl p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3"><div><div className="tm-label">knowledge coverage</div><h2 className="mt-1 text-base font-semibold">Indexed source fleet</h2></div><Badge>{enabled} enabled</Badge></div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {snapshot.sources.map((source) => <Link key={source.source_id} href="/sources" className="tm-command-source rounded-xl p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><span className={cn("tm-led", source.latest_run_status === "failed" && "red", source.locked && "amber")}/><span className="truncate text-xs font-semibold">{source.component}</span></div><div className="mt-2 truncate font-mono text-[9px] text-slate-700">{source.repository}</div></div><span className="font-mono text-[9px] text-cyan-300">{shortSha(source.snapshot_commit_sha)}</span></div><div className="mt-3 flex items-center justify-between text-[9px] text-slate-600"><span>{source.file_count} files</span><span>{source.version_ref ?? source.configured_ref}</span></div></Link>)}
          </div>
        </section>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
        <section className="tm-command-map rounded-2xl p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3"><div><div className="tm-label">ingestion activity</div><h2 className="mt-1 text-base font-semibold">Recent synchronization channel</h2></div><Link href="/ops" className="flex items-center gap-1 text-[10px] text-cyan-300">Open operations <ArrowRight className="size-3"/></Link></div>
          {recentRuns.length === 0 ? <div className="mt-5 rounded-xl border border-dashed border-white/6 p-8 text-center text-xs text-slate-700">No ingestion runs recorded yet.</div> : <>
            <div className="tm-activity-chart mt-6 flex h-36 items-end gap-2 overflow-hidden px-1">
              {recentRuns.map((run) => { const magnitude = Math.max(run.indexed_count, run.chunk_count); const height = Math.max(10, Math.round((magnitude / activityMax) * 100)); return <div key={run.run_id} className="group flex min-w-0 flex-1 flex-col items-center justify-end gap-2"><div className={cn("w-full max-w-[28px] rounded-t-md transition group-hover:brightness-125", run.status === "failed" ? "bg-red-300/55" : run.status === "running" ? "bg-amber-300/55" : "bg-cyan-300/50")} style={{ height: `${height}%` }} title={`${run.source_id}: ${run.indexed_count} indexed`}/><span className="max-w-full truncate font-mono text-[7px] text-slate-700">{run.source_id.replace("tractusx-", "tx-")}</span></div>; })}
            </div>
            <div className="mt-5 space-y-1.5">{snapshot.runs.slice(0, 5).map((run) => <div key={run.run_id} className="tm-run-row grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl px-3 py-2.5"><span className={cn("tm-led", run.status === "failed" && "red", run.status === "running" && "amber")}/><div className="min-w-0"><div className="truncate text-xs font-semibold">{run.source_id}</div><div className="mt-1 text-[9px] text-slate-600">{run.indexed_count} indexed · {run.chunk_count} chunks · {formatDate(run.started_at)}</div></div><Badge className={run.status === "failed" ? "text-red-300" : run.status === "running" ? "text-amber-300" : "text-emerald-300"}>{run.status}</Badge></div>)}</div>
          </>}
        </section>

        <div className="grid gap-4">
          <section className="tm-command-map rounded-2xl p-4 sm:p-5">
            <div className="flex items-center justify-between gap-3"><div><div className="tm-label">quality guard</div><h2 className="mt-1 text-base font-semibold">Human review signal</h2></div><ShieldCheck className="size-5 text-cyan-300"/></div>
            <div className="mt-5 grid grid-cols-3 gap-2"><div className="tm-well rounded-xl p-3"><div className="tm-label">pending</div><div className="mt-2 text-lg font-semibold text-amber-300">{pendingReviews}</div></div><div className="tm-well rounded-xl p-3"><div className="tm-label">promoted</div><div className="mt-2 text-lg font-semibold text-emerald-300">{promoted}</div></div><div className="tm-well rounded-xl p-3"><div className="tm-label">regressions</div><div className="mt-2 text-lg font-semibold text-cyan-200">{regressions}</div></div></div>
            <div className="mt-4 space-y-1.5">{snapshot.reviews.slice(0, 4).map((review) => <Link key={review.review_id} href="/quality" className="tm-command-review block rounded-xl p-3"><div className="flex items-center justify-between gap-3"><span className="tm-label">{review.trigger}</span><Badge className={review.status === "pending" ? "text-amber-300" : review.status === "promoted" ? "text-emerald-300" : ""}>{review.status}</Badge></div><div className="mt-2 line-clamp-2 text-[10px] leading-4 text-slate-500">{review.question}</div></Link>)}</div>
          </section>

          <section className="tm-command-map rounded-2xl p-4 sm:p-5">
            <div className="flex items-center justify-between gap-3"><div><div className="tm-label">active identity</div><h2 className="mt-1 text-base font-semibold">Session authority</h2></div><UserRoundCog className="size-5 text-cyan-300"/></div>
            <div className="mt-4 flex items-center gap-3"><div className="tm-orb grid size-11 place-items-center rounded-xl text-xs font-bold text-cyan-200">{identity.display_name.slice(0, 2).toUpperCase()}</div><div className="min-w-0"><div className="truncate text-sm font-semibold">{identity.display_name}</div><div className="mt-1 flex flex-wrap gap-2"><Badge className="text-cyan-300">{identity.role}</Badge><Badge>{identity.auth_type}</Badge></div></div></div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-[10px]"><div className="tm-well rounded-xl p-3"><div className="tm-label">control level</div><div className="mt-2 text-slate-300">{identity.role === "admin" ? "read + mutate" : "read operations"}</div></div><div className="tm-well rounded-xl p-3"><div className="tm-label">session boundary</div><div className="mt-2 text-slate-300">HttpOnly BFF</div></div></div>
            {identity.role === "admin" ? <Link href="/admin" className="tm-control mt-3 flex h-9 items-center justify-center gap-2 rounded-lg text-[10px] font-semibold">Manage access <ArrowRight className="size-3"/></Link> : <div className="mt-3 text-[9px] leading-4 text-slate-700">Administrative mutation controls remain hidden for operator identities.</div>}
          </section>
        </div>
      </div>
    </div>
  );
}
