"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Activity,
  AlertTriangle,
  Check,
  ChevronRight,
  CircleDot,
  Copy,
  Database,
  Filter,
  GitCommitHorizontal,
  KeyRound,
  Layers3,
  LockKeyhole,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  ServerCog,
  ShieldCheck,
  TerminalSquare,
  UserRoundCog,
  Users,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AdminPasswordManager } from "@/components/admin-password-manager";
import type { MissionView } from "@/components/mission-control";
import type {
  Identity,
  ManagedUser,
  OpsSummary,
  QualityReview,
  RunStatus,
  SourceStatus,
  UserRole,
} from "@/lib/types";
import { cn, formatDate, shortSha } from "@/lib/utils";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend${path}`, { cache: "no-store", ...init });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? `Request failed: ${response.status}`);
  return payload as T;
}

type Tone = "cyan" | "green" | "amber" | "red" | "neutral";

const toneText: Record<Tone, string> = {
  cyan: "text-cyan-200",
  green: "text-emerald-300",
  amber: "text-amber-300",
  red: "text-red-300",
  neutral: "text-slate-300",
};

function Stat({ label, value, tone = "cyan", detail }: { label: string; value: string | number; tone?: Tone; detail?: string }) {
  return (
    <div className="tm-stat tm-panel rounded-xl p-4">
      <div className="tm-label">{label}</div>
      <div className={cn("mt-3 text-2xl font-semibold tracking-tight", toneText[tone])}>{value}</div>
      {detail && <div className="mt-1 text-[10px] text-slate-600">{detail}</div>}
    </div>
  );
}

function DeckHeader({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="tm-label">{eyebrow}</div>
        <h1 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-600">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

function LoadingDeck() {
  return (
    <div className="tm-panel grid min-h-0 flex-1 place-items-center rounded-2xl">
      <div className="text-center">
        <div className="tm-orb mx-auto grid size-12 place-items-center rounded-xl"><RefreshCw className="size-4 animate-spin text-cyan-300"/></div>
        <div className="tm-label mt-4">reading control plane</div>
      </div>
    </div>
  );
}

function ErrorStrip({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="mb-4 rounded-xl border border-red-300/15 bg-red-300/5 p-3 text-xs text-red-200">{message}</div>;
}

function EmptyState({ icon: Icon, title, text }: { icon: typeof Search; title: string; text: string }) {
  return (
    <div className="grid min-h-52 place-items-center rounded-2xl border border-dashed border-white/6 p-8 text-center">
      <div className="max-w-sm"><Icon className="mx-auto size-5 text-slate-700"/><div className="mt-3 text-sm font-semibold text-slate-400">{title}</div><p className="mt-2 text-xs leading-5 text-slate-700">{text}</p></div>
    </div>
  );
}

function SearchBar({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) {
  return (
    <label className="tm-search flex h-10 min-w-0 flex-1 items-center gap-2 rounded-xl px-3">
      <Search className="size-3.5 shrink-0 text-slate-600"/>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="min-w-0 flex-1 bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-700"/>
      {value && <button onClick={() => onChange("")} className="text-slate-700 hover:text-slate-400" aria-label="Clear search"><X className="size-3.5"/></button>}
    </label>
  );
}

function FilterButton({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return <button onClick={onClick} className={cn("tm-filter rounded-lg px-3 py-2 text-[10px] font-semibold uppercase tracking-[.12em]", active ? "text-cyan-200" : "text-slate-600")}>{children}</button>;
}

function StatusDot({ status }: { status?: string | null }) {
  const tone = status === "failed" || status === "error" || status === "disabled" ? "red" : status === "running" || status === "locked" || status === "pending" ? "amber" : "";
  return <span className={`tm-led ${tone}`}/>;
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return <div className="flex items-start justify-between gap-4 border-b border-white/[.035] py-2.5 last:border-0"><span className="tm-label shrink-0">{label}</span><div className="min-w-0 text-right text-[11px] text-slate-400">{children}</div></div>;
}

function SourceDeck({ identity }: { identity: Identity }) {
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "healthy" | "failed" | "locked">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(() => json<SourceStatus[]>("/v1/ops/sources").then((items) => { setSources(items); setError(null); }).catch((e) => setError(e.message)).finally(() => setLoading(false)), []);
  useEffect(() => { void load(); }, [load]);

  async function sync(sourceId: string) {
    setBusy(sourceId); setError(null);
    try { await json(`/v1/ops/sources/${sourceId}/sync`, { method: "POST" }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Sync failed"); }
    finally { setBusy(null); }
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return sources.filter((source) => {
      const matchesQuery = !needle || [source.source_id, source.component, source.repository, source.configured_ref, source.version_ref ?? ""].some((value) => value.toLowerCase().includes(needle));
      const matchesFilter = filter === "all" || (filter === "failed" && source.latest_run_status === "failed") || (filter === "locked" && source.locked) || (filter === "healthy" && source.latest_run_status !== "failed" && !source.locked);
      return matchesQuery && matchesFilter;
    });
  }, [filter, query, sources]);

  const selected = sources.find((source) => source.source_id === selectedId) ?? null;
  const failedCount = sources.filter((source) => source.latest_run_status === "failed").length;
  const lockedCount = sources.filter((source) => source.locked).length;
  const totalFiles = sources.reduce((sum, source) => sum + source.file_count, 0);

  if (loading) return <LoadingDeck />;
  return (
    <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
      <DeckHeader eyebrow="knowledge plane" title="Versioned source registry" subtitle="Inspect every enabled knowledge source, its pinned ref, indexed snapshot and latest ingestion state. Admins can synchronize sources directly from this surface." action={<Badge className="text-cyan-300"><Database className="size-3"/>{sources.length} registered</Badge>}/>
      <ErrorStrip message={error}/>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="sources" value={sources.length} detail="registry entries"/>
        <Stat label="indexed files" value={totalFiles.toLocaleString()} tone="green" detail="across current snapshots"/>
        <Stat label="failed" value={failedCount} tone={failedCount ? "red" : "green"} detail="latest ingestion run"/>
        <Stat label="locked" value={lockedCount} tone={lockedCount ? "amber" : "green"} detail="sync protection"/>
      </div>
      <div className="mt-5 flex flex-col gap-2 lg:flex-row lg:items-center">
        <SearchBar value={query} onChange={setQuery} placeholder="Search component, repository, ref…"/>
        <div className="flex shrink-0 gap-1 overflow-x-auto"><FilterButton active={filter === "all"} onClick={() => setFilter("all")}>All</FilterButton><FilterButton active={filter === "healthy"} onClick={() => setFilter("healthy")}>Healthy</FilterButton><FilterButton active={filter === "failed"} onClick={() => setFilter("failed")}>Failed</FilterButton><FilterButton active={filter === "locked"} onClick={() => setFilter("locked")}>Locked</FilterButton></div>
      </div>
      <div className={cn("mt-4 grid gap-4", selected ? "xl:grid-cols-[minmax(0,1fr)_340px]" : "") }>
        <div className="grid content-start gap-3 lg:grid-cols-2">
          {filtered.map((source) => (
            <motion.button layout key={source.source_id} onClick={() => setSelectedId(source.source_id)} className={cn("tm-console-card rounded-2xl p-4 text-left", selectedId === source.source_id && "is-selected")}>
              <div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex items-center gap-2"><StatusDot status={source.latest_run_status === "failed" ? "failed" : source.locked ? "locked" : "ok"}/><span className="truncate text-sm font-semibold">{source.component}</span></div><div className="mt-2 truncate font-mono text-[10px] text-slate-600">{source.repository}</div></div><Badge>{source.priority}</Badge></div>
              <div className="mt-5 grid grid-cols-3 gap-2"><div className="tm-panel rounded-lg p-3"><div className="tm-label">files</div><div className="mt-2 font-mono text-sm text-slate-200">{source.file_count}</div></div><div className="tm-panel rounded-lg p-3"><div className="tm-label">snapshot</div><div className="mt-2 font-mono text-sm text-cyan-200">{shortSha(source.snapshot_commit_sha)}</div></div><div className="tm-panel rounded-lg p-3"><div className="tm-label">ref</div><div className="mt-2 truncate font-mono text-sm text-amber-200">{source.version_ref ?? source.configured_ref}</div></div></div>
              <div className="mt-4 flex items-center justify-between border-t border-white/5 pt-3"><div className="text-[9px] text-slate-700">{formatDate(source.updated_at)} · {source.latest_run_status ?? "no run"}</div><ChevronRight className="size-3.5 text-slate-700"/></div>
            </motion.button>
          ))}
          {filtered.length === 0 && <div className="lg:col-span-2"><EmptyState icon={Database} title="No sources match" text="Adjust the search or status filter. Registry data itself has not been changed."/></div>}
        </div>
        {selected && (
          <motion.aside initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} className="tm-inspector h-fit rounded-2xl p-4 xl:sticky xl:top-0">
            <div className="flex items-start justify-between gap-3"><div><div className="tm-label">source inspector</div><h2 className="mt-2 text-base font-semibold">{selected.component}</h2></div><Button variant="ghost" size="icon" onClick={() => setSelectedId(null)}><X className="size-4"/></Button></div>
            <div className="mt-4 rounded-xl border border-white/[.04] bg-black/20 p-3 font-mono text-[10px] leading-5 text-slate-500 break-all">{selected.repository}</div>
            <div className="mt-4"><DetailRow label="source id"><span className="font-mono text-cyan-200">{selected.source_id}</span></DetailRow><DetailRow label="configured ref"><span className="font-mono">{selected.configured_ref}</span></DetailRow><DetailRow label="version ref"><span className="font-mono">{selected.version_ref ?? "—"}</span></DetailRow><DetailRow label="snapshot"><span className="font-mono text-cyan-200">{selected.snapshot_commit_sha ?? "—"}</span></DetailRow><DetailRow label="files">{selected.file_count.toLocaleString()}</DetailRow><DetailRow label="latest run"><span className={selected.latest_run_status === "failed" ? "text-red-300" : "text-emerald-300"}>{selected.latest_run_status ?? "none"}</span></DetailRow><DetailRow label="updated">{formatDate(selected.updated_at)}</DetailRow></div>
            {selected.latest_run_error && <div className="mt-4 rounded-xl border border-red-300/10 bg-red-300/5 p-3 text-[10px] leading-5 text-red-200">{selected.latest_run_error}</div>}
            {identity.role === "admin" && <Button variant="primary" className="mt-4 w-full" onClick={() => void sync(selected.source_id)} disabled={busy === selected.source_id || selected.locked}><RefreshCw className={cn("size-3.5", busy === selected.source_id && "animate-spin")}/>{selected.locked ? "Source locked" : busy === selected.source_id ? "Synchronizing…" : "Synchronize source"}</Button>}
          </motion.aside>
        )}
      </div>
    </div>
  );
}

function OpsDeck() {
  const [summary, setSummary] = useState<OpsSummary | null>(null);
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "running" | "succeeded" | "failed">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const [s, r] = await Promise.all([json<OpsSummary>("/v1/ops/summary"), json<RunStatus[]>("/v1/ops/runs?limit=50")]);
      setSummary(s); setRuns(r); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Ops unavailable"); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    void load(true);
    const timer = window.setInterval(() => void load(true), 15_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return runs.filter((run) => (!needle || [run.source_id, run.repository, run.run_id].some((value) => value.toLowerCase().includes(needle))) && (filter === "all" || run.status === filter));
  }, [filter, query, runs]);

  const selected = runs.find((run) => run.run_id === selectedId) ?? null;
  const totalChunks = runs.reduce((sum, run) => sum + run.chunk_count, 0);

  if (loading) return <LoadingDeck />;
  return (
    <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
      <DeckHeader eyebrow="runtime plane" title="Operations telemetry" subtitle="Live ingestion control surface with source coverage, runtime health and recent synchronization runs. This view refreshes automatically every 15 seconds." action={<Button size="sm" onClick={() => void load()} disabled={refreshing}><RefreshCw className={cn("size-3.5", refreshing && "animate-spin")}/>{refreshing ? "Refreshing" : "Refresh"}</Button>}/>
      <ErrorStrip message={error}/>
      {summary && <div className="grid grid-cols-2 gap-3 lg:grid-cols-5"><Stat label="indexed sources" value={`${summary.indexed_sources}/${summary.enabled_sources}`} tone="green"/><Stat label="running" value={summary.running_sources} tone={summary.running_sources ? "amber" : "green"}/><Stat label="failed" value={summary.failed_sources} tone={summary.failed_sources ? "red" : "green"}/><Stat label="redis" value={summary.redis_ok ? "ONLINE" : "DOWN"} tone={summary.redis_ok ? "green" : "red"}/><Stat label="recent chunks" value={totalChunks.toLocaleString()} detail="shown run window"/></div>}
      <div className="mt-5 flex flex-col gap-2 lg:flex-row lg:items-center"><SearchBar value={query} onChange={setQuery} placeholder="Search source, repository or run id…"/><div className="flex shrink-0 gap-1 overflow-x-auto"><FilterButton active={filter === "all"} onClick={() => setFilter("all")}>All</FilterButton><FilterButton active={filter === "running"} onClick={() => setFilter("running")}>Running</FilterButton><FilterButton active={filter === "succeeded"} onClick={() => setFilter("succeeded")}>Succeeded</FilterButton><FilterButton active={filter === "failed"} onClick={() => setFilter("failed")}>Failed</FilterButton></div></div>
      <div className={cn("mt-4 grid gap-4", selected ? "xl:grid-cols-[minmax(0,1fr)_360px]" : "") }>
        <div className="tm-well rounded-2xl p-3">
          <div className="mb-3 flex items-center justify-between gap-3 px-1"><div className="flex items-center gap-2"><ServerCog className="size-4 text-cyan-300"/><span className="text-sm font-semibold">Ingestion run channel</span></div><span className="tm-label">{filtered.length} visible</span></div>
          <div className="space-y-1.5">
            {filtered.map((run) => (
              <button key={run.run_id} onClick={() => setSelectedId(run.run_id)} className={cn("tm-run-row grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl px-3 py-3 text-left", selectedId === run.run_id && "is-selected")}>
                <StatusDot status={run.status}/><div className="min-w-0"><div className="flex items-center gap-2"><span className="truncate text-xs font-semibold">{run.source_id}</span><span className="tm-mono text-[9px] text-slate-700">{shortSha(run.run_id)}</span></div><div className="mt-1 truncate text-[10px] text-slate-600">{run.indexed_count} indexed · {run.chunk_count} chunks · +{run.added_count} ~{run.modified_count} -{run.deleted_count}</div>{run.error_message && <div className="mt-1 truncate text-[10px] text-red-300">{run.error_message}</div>}</div><div className="text-right"><Badge className={run.status === "failed" ? "text-red-300" : run.status === "running" ? "text-amber-300" : "text-emerald-300"}>{run.status}</Badge><div className="mt-1 text-[9px] text-slate-700">{formatDate(run.started_at)}</div></div>
              </button>
            ))}
            {filtered.length === 0 && <EmptyState icon={TerminalSquare} title="No runs match" text="Try a different source search or status filter."/>}
          </div>
        </div>
        {selected && <motion.aside initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} className="tm-inspector h-fit rounded-2xl p-4 xl:sticky xl:top-0"><div className="flex items-start justify-between gap-3"><div><div className="tm-label">run inspector</div><h2 className="mt-2 text-base font-semibold">{selected.source_id}</h2><div className="mt-1 font-mono text-[10px] text-slate-600">{selected.run_id}</div></div><Button variant="ghost" size="icon" onClick={() => setSelectedId(null)}><X className="size-4"/></Button></div><div className="mt-4 grid grid-cols-3 gap-2"><div className="tm-panel rounded-lg p-3 text-center"><div className="tm-label">indexed</div><div className="mt-2 font-mono text-sm text-cyan-200">{selected.indexed_count}</div></div><div className="tm-panel rounded-lg p-3 text-center"><div className="tm-label">chunks</div><div className="mt-2 font-mono text-sm text-slate-200">{selected.chunk_count}</div></div><div className="tm-panel rounded-lg p-3 text-center"><div className="tm-label">fetched</div><div className="mt-2 font-mono text-sm text-amber-200">{selected.fetched_count}</div></div></div><div className="mt-4"><DetailRow label="status"><span className={selected.status === "failed" ? "text-red-300" : selected.status === "running" ? "text-amber-300" : "text-emerald-300"}>{selected.status}</span></DetailRow><DetailRow label="discovered">{selected.discovered_count}</DetailRow><DetailRow label="added">+{selected.added_count}</DetailRow><DetailRow label="modified">~{selected.modified_count}</DetailRow><DetailRow label="deleted">-{selected.deleted_count}</DetailRow><DetailRow label="unchanged">{selected.unchanged_count}</DetailRow><DetailRow label="started">{formatDate(selected.started_at)}</DetailRow><DetailRow label="finished">{formatDate(selected.finished_at)}</DetailRow></div>{selected.error_message && <div className="mt-4 rounded-xl border border-red-300/10 bg-red-300/5 p-3 text-[10px] leading-5 text-red-200">{selected.error_message}</div>}</motion.aside>}
      </div>
    </div>
  );
}

type RootCause = "routing" | "retrieval" | "citation" | "generation" | "verification" | "source_data" | "versioning" | "other";
type BenchmarkKind = "retrieval" | "debug" | "answer";
const ROOT_CAUSES: RootCause[] = ["routing", "retrieval", "citation", "generation", "verification", "source_data", "versioning", "other"];

function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function QualityDeck({ identity }: { identity: Identity }) {
  const [reviews, setReviews] = useState<QualityReview[]>([]);
  const [summary, setSummary] = useState<{ review_counts: Record<string, number>; regression_cases: number } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rootCause, setRootCause] = useState<RootCause>("retrieval");
  const [benchmarkKind, setBenchmarkKind] = useState<BenchmarkKind>("answer");
  const [sourceIds, setSourceIds] = useState("");
  const [terms, setTerms] = useState("");
  const [expectedAbstain, setExpectedAbstain] = useState(false);
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "pending" | "promoted" | "dismissed">("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([json<{ review_counts: Record<string, number>; regression_cases: number }>("/v1/ops/quality/summary"), json<QualityReview[]>("/v1/ops/quality/reviews?limit=80")]);
      setSummary(s); setReviews(r); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Quality console unavailable"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const selected = reviews.find((review) => review.review_id === selectedId) ?? null;

  function selectReview(review: QualityReview) {
    setSelectedId(review.review_id);
    setRootCause((review.root_cause as RootCause | null) ?? "retrieval");
    setBenchmarkKind(review.intent === "debug" ? "debug" : "answer");
    setSourceIds(""); setTerms(""); setExpectedAbstain(false); setNote(review.reviewer_note ?? ""); setError(null);
  }

  async function decide(action: "dismiss" | "promote") {
    if (!selected) return;
    const expected_source_ids = splitCsv(sourceIds);
    const expected_terms = splitCsv(terms);
    if (action === "promote" && !expectedAbstain && expected_source_ids.length === 0 && expected_terms.length === 0) { setError("Promoted answerable cases need at least one expected source or term."); return; }
    setBusy(true); setError(null);
    try {
      const body: Record<string, unknown> = { action, root_cause: rootCause, reviewer_note: note || null };
      if (action === "promote") Object.assign(body, { benchmark_kind: benchmarkKind, expected_source_ids, expected_terms, expected_abstain: expectedAbstain });
      await json(`/v1/ops/quality/reviews/${selected.review_id}/decision`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      setSelectedId(null); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Review decision failed"); }
    finally { setBusy(false); }
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return reviews.filter((review) => (!needle || [review.question, review.answer ?? "", review.intent ?? "", review.root_cause ?? "", review.trigger].some((value) => value.toLowerCase().includes(needle))) && (filter === "all" || review.status === filter));
  }, [filter, query, reviews]);

  if (loading) return <LoadingDeck />;
  return (
    <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
      <DeckHeader eyebrow="trust plane" title="Human-reviewed quality loop" subtitle="Turn failures and negative feedback into reviewed regression cases. Raw feedback never promotes itself; every production benchmark remains human-controlled." action={<Badge className="text-emerald-300"><ShieldCheck className="size-3"/> regression guarded</Badge>}/>
      <ErrorStrip message={error}/>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat label="pending" value={summary?.review_counts.pending ?? 0} tone="amber" detail="needs human review"/><Stat label="promoted" value={summary?.review_counts.promoted ?? 0} tone="green" detail="accepted failures"/><Stat label="dismissed" value={summary?.review_counts.dismissed ?? 0} detail="not benchmark material"/><Stat label="regressions" value={summary?.regression_cases ?? 0} tone="cyan" detail="guarded cases"/></div>
      <div className="mt-5 flex flex-col gap-2 lg:flex-row lg:items-center"><SearchBar value={query} onChange={setQuery} placeholder="Search question, answer, intent, cause…"/><div className="flex shrink-0 gap-1 overflow-x-auto"><FilterButton active={filter === "all"} onClick={() => setFilter("all")}>All</FilterButton><FilterButton active={filter === "pending"} onClick={() => setFilter("pending")}>Pending</FilterButton><FilterButton active={filter === "promoted"} onClick={() => setFilter("promoted")}>Promoted</FilterButton><FilterButton active={filter === "dismissed"} onClick={() => setFilter("dismissed")}>Dismissed</FilterButton></div></div>
      <div className={cn("mt-4 grid gap-4", selected ? "xl:grid-cols-[minmax(0,1fr)_390px]" : "") }>
        <div className="grid content-start gap-3 lg:grid-cols-2">
          {filtered.map((review) => <button key={review.review_id} onClick={() => selectReview(review)} className={cn("tm-console-card rounded-2xl p-4 text-left", selectedId === review.review_id && "is-selected")}><div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2">{review.error_type ? <AlertTriangle className="size-4 text-red-300"/> : <Activity className="size-4 text-amber-300"/>}<span className="tm-label">{review.trigger}</span></div><Badge className={review.status === "pending" ? "text-amber-300" : review.status === "promoted" ? "text-emerald-300" : ""}>{review.status}</Badge></div><div className="mt-4 line-clamp-3 text-sm font-semibold leading-6 text-slate-200">{review.question}</div>{review.answer && <div className="mt-3 line-clamp-2 text-xs leading-5 text-slate-500">{review.answer}</div>}<div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">{review.intent && <Badge>{review.intent}</Badge>}{review.feedback_rating && <Badge className={review.feedback_rating === "down" ? "text-red-300" : "text-emerald-300"}>feedback {review.feedback_rating}</Badge>}{review.root_cause && <Badge>{review.root_cause}</Badge>}<span className="ml-auto text-[9px] text-slate-700">{formatDate(review.created_at)}</span></div></button>)}
          {filtered.length === 0 && <div className="lg:col-span-2"><EmptyState icon={ShieldCheck} title="No reviews match" text="The selected status and search terms returned no review items."/></div>}
        </div>
        {selected && <motion.aside initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} className="tm-inspector h-fit rounded-2xl p-4 xl:sticky xl:top-0"><div className="flex items-start justify-between gap-3"><div><div className="tm-label">quality inspector</div><h2 className="mt-2 text-sm font-semibold leading-6">{selected.question}</h2></div><Button variant="ghost" size="icon" onClick={() => setSelectedId(null)}><X className="size-4"/></Button></div>{selected.answer && <div className="tm-scrollbar mt-4 max-h-40 overflow-y-auto rounded-xl border border-white/[.04] bg-black/20 p-3 text-[11px] leading-5 text-slate-500">{selected.answer}</div>}<div className="mt-4"><DetailRow label="status"><Badge className={selected.status === "pending" ? "text-amber-300" : selected.status === "promoted" ? "text-emerald-300" : ""}>{selected.status}</Badge></DetailRow><DetailRow label="trigger">{selected.trigger}</DetailRow><DetailRow label="intent">{selected.intent ?? "—"}</DetailRow><DetailRow label="feedback">{selected.feedback_rating ?? "—"}</DetailRow><DetailRow label="root cause">{selected.root_cause ?? "unreviewed"}</DetailRow><DetailRow label="created">{formatDate(selected.created_at)}</DetailRow></div>{identity.role === "admin" && selected.status === "pending" && <div className="mt-5 border-t border-white/5 pt-4"><div className="mb-3 flex items-center gap-2"><CircleDot className="size-4 text-cyan-300"/><span className="text-xs font-semibold">Decision controls</span></div><div className="space-y-3"><label><span className="tm-label mb-2 block">root cause</span><select value={rootCause} onChange={(e) => setRootCause(e.target.value as RootCause)} className="tm-field h-10 w-full rounded-lg px-2 text-xs outline-none">{ROOT_CAUSES.map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label><span className="tm-label mb-2 block">benchmark</span><select value={benchmarkKind} onChange={(e) => setBenchmarkKind(e.target.value as BenchmarkKind)} className="tm-field h-10 w-full rounded-lg px-2 text-xs outline-none"><option value="answer">answer</option><option value="retrieval">retrieval</option><option value="debug">debug</option></select></label><label><span className="tm-label mb-2 block">reviewer note</span><textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className="tm-field w-full resize-none rounded-lg px-3 py-2 text-xs outline-none" placeholder="Why it failed and what good should look like"/></label><label><span className="tm-label mb-2 block">expected source ids</span><input value={sourceIds} onChange={(e) => setSourceIds(e.target.value)} className="tm-field h-10 w-full rounded-lg px-3 font-mono text-xs outline-none" placeholder="tractusx-edc, tractusx-sdk"/></label><label><span className="tm-label mb-2 block">expected terms</span><input value={terms} onChange={(e) => setTerms(e.target.value)} className="tm-field h-10 w-full rounded-lg px-3 font-mono text-xs outline-none" placeholder="TransferProcess, negotiation"/></label><label className="flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" checked={expectedAbstain} onChange={(e) => setExpectedAbstain(e.target.checked)} disabled={benchmarkKind !== "answer"}/><span>Expected abstention</span></label><div className="grid grid-cols-2 gap-2"><Button onClick={() => void decide("dismiss")} disabled={busy}>Dismiss</Button><Button variant="primary" onClick={() => void decide("promote")} disabled={busy}>{busy ? "Committing…" : "Promote"}</Button></div></div></div>}</motion.aside>}
      </div>
    </div>
  );
}

function AdminDeck() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [credential, setCredential] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => json<ManagedUser[]>("/v1/ops/users").then((items) => { setUsers(items); setError(null); }).catch((e) => setError(e.message)).finally(() => setLoading(false)), []);
  useEffect(() => { void load(); }, [load]);

  async function createUser() {
    if (!name.trim()) return;
    setBusy("create"); setError(null);
    try { const created = await json<ManagedUser & { api_key: string }>("/v1/ops/users", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ display_name: name, role }) }); setCredential(created.api_key); setCopied(false); setName(""); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Identity provisioning failed"); }
    finally { setBusy(null); }
  }

  async function patchUser(user: ManagedUser, body: Record<string, unknown>) {
    setBusy(user.user_id); setError(null);
    try { await json(`/v1/ops/users/${user.user_id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Identity update failed"); }
    finally { setBusy(null); }
  }

  async function rotate(user: ManagedUser) {
    setBusy(user.user_id); setError(null);
    try { const updated = await json<ManagedUser & { api_key: string }>(`/v1/ops/users/${user.user_id}/rotate`, { method: "POST" }); setCredential(updated.api_key); setCopied(false); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Key rotation failed"); }
    finally { setBusy(null); }
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return users.filter((user) => (!needle || [user.display_name, user.role, user.auth_type, user.api_key_prefix ?? ""].some((value) => value.toLowerCase().includes(needle))) && (filter === "all" || (filter === "enabled" ? user.enabled : !user.enabled)));
  }, [filter, query, users]);
  const enabledCount = users.filter((user) => user.enabled).length;
  const adminCount = users.filter((user) => user.role === "admin").length;
  const oidcCount = users.filter((user) => user.auth_type !== "api_key").length;

  if (loading) return <LoadingDeck />;
  return (
    <div className="tm-panel tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-2xl p-4 sm:p-5">
      <DeckHeader eyebrow="identity plane" title="Users, roles & credentials" subtitle="Provision API identities, rotate credentials and control local access. OIDC identities remain governed by the external identity provider." action={<Badge className="text-cyan-300"><UserRoundCog className="size-3"/>{users.length} identities</Badge>}/>
      <ErrorStrip message={error}/>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat label="identities" value={users.length}/><Stat label="enabled" value={enabledCount} tone="green"/><Stat label="admins" value={adminCount} tone="amber"/><Stat label="external oidc" value={oidcCount} detail="IdP-managed roles"/></div>
      <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-center"><SearchBar value={query} onChange={setQuery} placeholder="Search name, role, auth type…"/><div className="flex shrink-0 gap-1"><FilterButton active={filter === "all"} onClick={() => setFilter("all")}>All</FilterButton><FilterButton active={filter === "enabled"} onClick={() => setFilter("enabled")}>Enabled</FilterButton><FilterButton active={filter === "disabled"} onClick={() => setFilter("disabled")}>Disabled</FilterButton></div></div>
          <div className="tm-well rounded-2xl p-3"><div className="space-y-2">{filtered.map((user) => <div key={user.user_id} className="tm-user-row flex flex-wrap items-center gap-3 rounded-xl p-3"><div className="grid size-10 place-items-center rounded-xl border border-white/8 bg-black/20 text-xs font-bold text-cyan-200">{user.display_name.slice(0,2).toUpperCase()}</div><div className="min-w-[170px] flex-1"><div className="truncate text-sm font-semibold">{user.display_name}</div><div className="mt-1 flex flex-wrap items-center gap-2"><Badge>{user.auth_type}</Badge>{user.api_key_prefix && <span className="tm-mono text-[9px] text-slate-700">{user.api_key_prefix}…</span>}</div></div>{user.auth_type === "api_key" ? <select value={user.role} disabled={busy === user.user_id} onChange={(e) => void patchUser(user, { role: e.target.value })} className="tm-field h-8 rounded-lg px-2 text-[10px] uppercase tracking-wider outline-none"><option value="user">user</option><option value="operator">operator</option><option value="admin">admin</option></select> : <Badge className="text-amber-300">{user.role} · IdP</Badge>}{user.auth_type === "api_key" && <Button size="sm" onClick={() => void rotate(user)} disabled={busy === user.user_id}><RotateCw className={cn("size-3.5", busy === user.user_id && "animate-spin")}/>Rotate</Button>}<button disabled={busy === user.user_id} onClick={() => void patchUser(user, { enabled: !user.enabled })} className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-slate-500 disabled:opacity-40"><StatusDot status={user.enabled ? "ok" : "disabled"}/>{user.enabled ? "enabled" : "disabled"}</button></div>)}{filtered.length === 0 && <EmptyState icon={Users} title="No identities match" text="Adjust the search or access-state filter."/>}</div></div>
        </div>
        <div className="space-y-4">
          <AdminPasswordManager />
          <div className="tm-inspector rounded-2xl p-4"><div className="mb-4 flex items-center gap-2"><Plus className="size-4 text-cyan-300"/><span className="text-sm font-semibold">Provision API identity</span></div><label className="tm-label">display name</label><input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void createUser(); }} className="tm-field mt-2 w-full rounded-xl px-3 py-2.5 text-sm outline-none" placeholder="Engineering operator"/><label className="tm-label mt-4 block">role</label><div className="mt-2 grid grid-cols-3 gap-2">{(["user","operator","admin"] as UserRole[]).map((item) => <button key={item} onClick={() => setRole(item)} className={cn("tm-control rounded-lg px-2 py-2 text-[10px] uppercase tracking-wider", role === item ? "text-cyan-200" : "text-slate-500")}>{item}</button>)}</div><Button variant="primary" className="mt-4 w-full" onClick={() => void createUser()} disabled={!name.trim() || busy === "create"}><KeyRound className="size-4"/>{busy === "create" ? "Provisioning…" : "Create identity"}</Button></div>
          {credential && <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-2xl border border-amber-300/15 bg-amber-300/5 p-4"><div className="flex items-center justify-between"><div><div className="tm-label text-amber-300">one-time credential</div><div className="mt-1 text-xs text-amber-100/70">Copy it now. It will not be shown again.</div></div><button onClick={() => setCredential(null)} className="text-amber-200/50 hover:text-amber-200"><X className="size-4"/></button></div><div className="mt-3 break-all rounded-xl bg-black/25 p-3 font-mono text-[10px] leading-5 text-amber-100">{credential}</div><Button className="mt-3 w-full" onClick={async () => { await navigator.clipboard.writeText(credential); setCopied(true); window.setTimeout(() => setCopied(false), 1200); }}>{copied ? <Check className="size-3.5 text-emerald-300"/> : <Copy className="size-3.5"/>}{copied ? "Copied" : "Copy credential"}</Button></motion.div>}
        </div>
      </div>
    </div>
  );
}

export function DataDeck({ view, identity }: { view: Exclude<MissionView, "chat">; identity: Identity }) {
  if (view === "sources") return <SourceDeck identity={identity}/>;
  if (view === "ops") return <OpsDeck/>;
  if (view === "quality") return <QualityDeck identity={identity}/>;
  return <AdminDeck/>;
}
