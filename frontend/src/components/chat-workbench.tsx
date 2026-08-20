"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowUp,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  CornerDownLeft,
  ExternalLink,
  GitBranch,
  History,
  Layers3,
  MessageSquarePlus,
  RotateCw,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  ThumbsDown,
  ThumbsUp,
  X,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  AnswerCitation,
  ConversationHistory,
  ConversationSummary,
  GroundedAnswer,
} from "@/lib/types";
import { formatDate, shortSha } from "@/lib/utils";

type UserMessage = { id: string; role: "user"; text: string };
type AssistantMessage = {
  id: string;
  role: "assistant";
  text: string;
  payload?: GroundedAnswer;
  historical?: boolean;
};
type ChatMessage = UserMessage | AssistantMessage;
type LiveAssistantMessage = AssistantMessage & { payload: GroundedAnswer };

const QUICK_PROMPTS = [
  { label: "Debug EDC", prompt: "Why would an EDC transfer process stay in REQUESTED?", icon: Terminal },
  { label: "Trace APIs", prompt: "Show the SDK APIs involved in policy negotiation", icon: GitBranch },
  { label: "Inspect model", prompt: "Which semantic-model files define the relevant aspect?", icon: Layers3 },
  { label: "Compare refs", prompt: "Compare this behavior across a pinned ref", icon: Zap },
];

function hasPayload(message: ChatMessage): message is LiveAssistantMessage {
  return message.role === "assistant" && message.payload !== undefined;
}

function AnswerBody({ payload, onCitation }: { payload: GroundedAnswer; onCitation: (item: AnswerCitation) => void }) {
  const citationMap = new Map(payload.citations.map((item) => [`[${item.citation_id}]`, item]));
  return (
    <div className="space-y-4">
      <div className="whitespace-pre-wrap text-[15px] leading-7 text-slate-200">
        {payload.answer.split(/(\[S\d+\])/g).map((part, index) => {
          const citation = citationMap.get(part);
          if (!citation) return <span key={`${part}-${index}`}>{part}</span>;
          return (
            <button
              key={`${part}-${index}`}
              onClick={() => onCitation(citation)}
              className="tm-citation mx-1 inline-flex translate-y-[-1px] rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold text-cyan-200"
            >
              {citation.citation_id}
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
        <Badge className={payload.grounded ? "border-emerald-300/15 text-emerald-300" : "text-amber-300"}>
          <ShieldCheck className="size-3" /> {payload.grounded ? "grounded" : "guarded"}
        </Badge>
        <Badge>{payload.evidence_count} evidence</Badge>
        {payload.route?.intent && <Badge className="text-cyan-300">route · {payload.route.intent}</Badge>}
        {payload.verification && <Badge className={payload.verification.passed ? "text-emerald-300" : "text-red-300"}>{payload.verification.claims.length} claims</Badge>}
        {payload.model && <Badge>{payload.model}</Badge>}
      </div>
    </div>
  );
}

function HistoricalAnswer({ text }: { text: string }) {
  return (
    <div className="space-y-3">
      <div className="whitespace-pre-wrap text-[15px] leading-7 text-slate-300">{text}</div>
      <Badge className="text-slate-500"><Clock3 className="size-3" /> historical turn · provenance not rehydrated</Badge>
    </div>
  );
}

function Score({ label, value }: { label: string; value?: number | null }) {
  const normalized = value == null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-[10px] uppercase tracking-[.12em] text-slate-500">
        <span>{label}</span><span className="tm-mono text-slate-300">{value == null ? "—" : value.toFixed(4)}</span>
      </div>
      <div className="tm-meter"><span style={{ width: `${Math.max(4, normalized * 100)}%` }} /></div>
    </div>
  );
}

function Inspector({ citation, answer }: { citation: AnswerCitation | null; answer: GroundedAnswer | null }) {
  const [copied, setCopied] = useState(false);
  return (
    <aside className="tm-panel tm-desktop-only flex min-h-0 w-[370px] shrink-0 flex-col rounded-2xl p-3">
      <div className="mb-3 flex items-center justify-between px-1">
        <div><div className="tm-label">Evidence inspector</div><div className="mt-1 text-sm font-semibold">Provenance channel</div></div>
        <div className="flex items-center gap-2"><span className="tm-led cyan" /><span className="tm-label">live</span></div>
      </div>
      <div className="tm-well tm-scanline flex min-h-0 flex-1 flex-col rounded-xl p-4">
        {!citation ? (
          <div className="m-auto max-w-[250px] text-center">
            <div className="tm-orb mx-auto mb-5 grid size-14 place-items-center rounded-2xl"><Search className="size-5 text-cyan-200" /></div>
            <div className="text-sm font-semibold text-slate-200">Open an evidence marker</div>
            <p className="mt-2 text-xs leading-5 text-slate-600">Every live citation exposes repository, immutable commit, file range, retrieval path and claim verification.</p>
          </div>
        ) : (
          <div className="tm-scrollbar space-y-5 overflow-y-auto pr-1">
            <div>
              <div className="flex items-center justify-between"><Badge className="text-cyan-300">{citation.citation_id}</Badge><Badge>{citation.component}</Badge></div>
              <div className="mt-3 break-all text-sm font-semibold text-slate-100">{citation.repository}</div>
              <div className="mt-1 break-all font-mono text-[11px] leading-5 text-slate-500">{citation.path}:{citation.start_line}-{citation.end_line}</div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="tm-panel rounded-lg p-3"><div className="tm-label">content commit</div><div className="mt-2 font-mono text-xs text-cyan-200">{shortSha(citation.commit_sha, 10)}</div></div>
              <div className="tm-panel rounded-lg p-3"><div className="tm-label">snapshot</div><div className="mt-2 font-mono text-xs text-amber-200">{shortSha(citation.snapshot_commit_sha, 10)}</div></div>
            </div>
            <div className="space-y-3">
              <Score label="retrieval" value={citation.retrieval_score} />
              <Score label="reranker" value={citation.rerank_score} />
              {citation.debug_score != null && <Score label="debug lane" value={citation.debug_score} />}
            </div>
            <div>
              <div className="tm-label mb-2">retrieval methods</div>
              <div className="flex flex-wrap gap-1.5">{citation.retrieval_methods.map((method) => <Badge key={method}>{method}</Badge>)}</div>
            </div>
            {answer?.route && (
              <div className="border-t border-white/5 pt-4">
                <div className="tm-label mb-2">router decision</div>
                <div className="space-y-2 text-xs text-slate-400">
                  <div className="flex justify-between"><span>intent</span><span className="font-mono text-cyan-200">{answer.route.intent}</span></div>
                  <div className="flex justify-between"><span>ref</span><span className="font-mono text-slate-300">{answer.route.ref ?? "automatic"}</span></div>
                  {answer.route.source_ids.length > 0 && <div className="flex flex-wrap gap-1.5 pt-1">{answer.route.source_ids.map((source) => <Badge key={source}>{source}</Badge>)}</div>}
                  {answer.route.reasons.map((reason) => <div key={reason} className="rounded-md bg-white/[.025] px-2 py-1.5 font-mono text-[10px]">{reason}</div>)}
                </div>
              </div>
            )}
            {answer?.verification && (
              <div className="border-t border-white/5 pt-4">
                <div className="mb-2 flex items-center gap-2"><CheckCircle2 className={answer.verification.passed ? "size-4 text-emerald-300" : "size-4 text-red-300"} /><span className="text-xs font-semibold">Claim verification {answer.verification.passed ? "passed" : "failed"}</span></div>
                <div className="mb-3 text-[11px] text-slate-500">{answer.verification.claims.length} atomic claims · {answer.verification.unsupported_claim_count} unsupported</div>
                <div className="space-y-1.5">
                  {answer.verification.claims.slice(0, 8).map((claim, index) => (
                    <div key={`${claim.claim}-${index}`} className="rounded-lg border border-white/[.035] bg-white/[.018] p-2.5">
                      <div className="flex gap-2"><span className={`tm-led mt-1 shrink-0 ${claim.supported ? "" : "red"}`}/><p className="text-[10px] leading-5 text-slate-400">{claim.claim}</p></div>
                      {claim.citation_ids.length > 0 && <div className="mt-2 flex flex-wrap gap-1 pl-4">{claim.citation_ids.map((id) => <span key={id} className="font-mono text-[9px] text-cyan-300">{id}</span>)}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="flex gap-2">
              <Button size="sm" className="flex-1" onClick={async () => { await navigator.clipboard.writeText(`${citation.repository}@${citation.commit_sha}:${citation.path}#L${citation.start_line}-L${citation.end_line}`); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? "Copied" : "Copy ref"}
              </Button>
              <a className="tm-control inline-flex size-8 items-center justify-center rounded-lg" href={citation.source_url} target="_blank" rel="noreferrer" aria-label="Open immutable source"><ExternalLink className="size-3.5" /></a>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

function MobileInspector({ citation, onClose }: { citation: AnswerCitation | null; onClose: () => void }) {
  if (!citation) return null;
  return (
    <div className="tm-mobile-only fixed inset-x-2 bottom-2 z-50">
      <motion.div initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="tm-shell rounded-2xl p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><Badge className="text-cyan-300">{citation.citation_id} · {citation.component}</Badge><div className="mt-2 truncate text-sm font-semibold">{citation.repository}</div><div className="mt-1 truncate font-mono text-[10px] text-slate-500">{citation.path}:{citation.start_line}-{citation.end_line}</div></div>
          <Button variant="ghost" size="icon" onClick={onClose}><X className="size-4" /></Button>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]"><div className="tm-well rounded-lg p-2"><span className="tm-label">commit</span><div className="mt-1 font-mono text-cyan-200">{shortSha(citation.commit_sha, 10)}</div></div><div className="tm-well rounded-lg p-2"><span className="tm-label">rerank</span><div className="mt-1 font-mono text-amber-200">{citation.rerank_score?.toFixed(4) ?? "—"}</div></div></div>
        <a href={citation.source_url} target="_blank" rel="noreferrer" className="tm-control mt-3 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg text-xs font-semibold"><ExternalLink className="size-3.5" /> Open immutable source</a>
      </motion.div>
    </div>
  );
}

function SessionDrawer({
  open,
  items,
  currentId,
  loading,
  onOpen,
  onNew,
  onClose,
}: {
  open: boolean;
  items: ConversationSummary[];
  currentId: string | null;
  loading: boolean;
  onOpen: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <motion.aside initial={{ x: -24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} className="tm-shell absolute bottom-[92px] left-3 top-[54px] z-30 flex w-[300px] flex-col rounded-2xl p-3 shadow-2xl">
      <div className="mb-3 flex items-center justify-between"><div><div className="tm-label">Session memory</div><div className="mt-1 text-sm font-semibold">Owned conversations</div></div><Button variant="ghost" size="icon" onClick={onClose}><X className="size-4"/></Button></div>
      <Button variant="primary" size="sm" onClick={onNew}><MessageSquarePlus className="size-3.5"/>New conversation</Button>
      <div className="tm-scrollbar mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto">
        {loading && <div className="p-4 text-center tm-label">loading sessions</div>}
        {!loading && items.length === 0 && <div className="p-5 text-center text-xs leading-5 text-slate-600">No owned conversations yet.</div>}
        {items.map((item) => (
          <button key={item.conversation_id} onClick={() => onOpen(item.conversation_id)} className={`w-full rounded-xl border px-3 py-3 text-left transition ${currentId === item.conversation_id ? "border-cyan-300/15 bg-cyan-300/[.06]" : "border-white/[.035] bg-white/[.018] hover:bg-white/[.04]"}`}>
            <div className="flex items-center gap-2"><span className={`tm-led ${currentId === item.conversation_id ? "cyan" : ""}`}/><span className="tm-mono text-[10px] text-slate-300">{shortSha(item.conversation_id, 12)}</span></div>
            <div className="mt-2 text-[10px] text-slate-600">updated {formatDate(item.updated_at)}</div>
          </button>
        ))}
      </div>
    </motion.aside>
  );
}

function ProcessingRail() {
  const stages = ["route", "retrieve", "rerank", "verify"];
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="tm-processing rounded-xl px-3 py-3">
      <div className="mb-2 flex items-center gap-2"><Sparkles className="size-3.5 text-cyan-300"/><span className="tm-label">grounding answer</span></div>
      <div className="flex flex-wrap items-center gap-1.5">
        {stages.map((stage, index) => <div key={stage} className="flex items-center gap-1.5"><span className="tm-stage"><span className="tm-led cyan"/>{stage}</span>{index < stages.length - 1 && <span className="text-[9px] text-slate-700">→</span>}</div>)}
      </div>
    </motion.div>
  );
}

export function ChatWorkbench() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedQuestion, setLastFailedQuestion] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<AnswerCitation | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "up" | "down">>({});
  const [copiedAnswer, setCopiedAnswer] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const latestAnswer = useMemo(() => messages.filter(hasPayload).at(-1)?.payload ?? null, [messages]);

  const loadConversations = useCallback(async () => {
    try {
      const response = await fetch("/api/backend/v1/conversations?limit=100", { cache: "no-store" });
      if (response.ok) setConversations(await response.json());
    } catch {
      // Chat remains usable if conversation listing is temporarily unavailable.
    }
  }, []);

  useEffect(() => { void loadConversations(); }, [loadConversations]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, error]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
      if (event.key === "Escape") {
        setHistoryOpen(false);
        setSelectedCitation(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function newConversation() {
    setMessages([]);
    setConversationId(null);
    setSelectedCitation(null);
    setError(null);
    setLastFailedQuestion(null);
    setHistoryOpen(false);
    requestAnimationFrame(() => composerRef.current?.focus());
  }

  async function openConversation(id: string) {
    setHistoryLoading(true); setError(null);
    try {
      const response = await fetch(`/api/backend/v1/conversations/${encodeURIComponent(id)}?limit=100`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Unable to load conversation");
      const history = payload as ConversationHistory;
      const restored: ChatMessage[] = history.turns.flatMap((turn) => [
        { id: crypto.randomUUID(), role: "user" as const, text: turn.question },
        { id: crypto.randomUUID(), role: "assistant" as const, text: turn.answer, historical: true },
      ]);
      setMessages(restored);
      setConversationId(history.conversation_id);
      setSelectedCitation(null);
      setHistoryOpen(false);
      setLastFailedQuestion(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load conversation");
    } finally { setHistoryLoading(false); }
  }

  async function send(override?: string) {
    const value = (override ?? question).trim();
    if (!value || pending) return;
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", text: value };
    setMessages((current) => [...current, userMessage]);
    setQuestion(""); setPending(true); setError(null); setLastFailedQuestion(null);
    try {
      const response = await fetch("/api/backend/v1/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: value, conversation_id: conversationId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Answer generation failed");
      const answer = payload as GroundedAnswer;
      if (answer.conversation_id) setConversationId(answer.conversation_id);
      if (answer.citations[0]) setSelectedCitation(answer.citations[0]);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: answer.answer, payload: answer }]);
      void loadConversations();
    } catch (cause) {
      setLastFailedQuestion(value);
      setError(cause instanceof Error ? cause.message : "Unable to reach TractusMind");
    } finally { setPending(false); }
  }

  async function rate(answer: GroundedAnswer, rating: "up" | "down") {
    if (!answer.interaction_id) return;
    try {
      const response = await fetch("/api/backend/v1/feedback", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ interaction_id: answer.interaction_id, rating }),
      });
      if (!response.ok) throw new Error("Feedback could not be recorded");
      setFeedback((current) => ({ ...current, [answer.interaction_id!]: rating }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Feedback could not be recorded");
    }
  }

  async function copyAnswer(message: LiveAssistantMessage) {
    await navigator.clipboard.writeText(message.payload.answer);
    setCopiedAnswer(message.id);
    window.setTimeout(() => setCopiedAnswer(null), 1200);
  }

  return (
    <div className="flex min-h-0 flex-1 gap-3">
      <section className="tm-panel relative flex min-w-0 flex-1 flex-col rounded-2xl p-3">
        <div className="mb-3 flex items-center justify-between px-1">
          <div><div className="tm-label">AI engineering copilot</div><h1 className="mt-1 text-base font-semibold tracking-tight">Grounded workbench</h1></div>
          <div className="flex items-center gap-1.5">
            <Button variant="ghost" size="sm" onClick={() => setHistoryOpen((value) => !value)}><History className="size-3.5"/><span className="hidden sm:inline">Sessions</span></Button>
            <Button variant="ghost" size="sm" onClick={newConversation}><MessageSquarePlus className="size-3.5"/><span className="hidden sm:inline">New</span></Button>
            <div className="ml-1 hidden items-center gap-2 sm:flex"><span className="tm-led" /><span className="tm-label">guard armed</span></div>
          </div>
        </div>
        <SessionDrawer open={historyOpen} items={conversations} currentId={conversationId} loading={historyLoading} onOpen={(id) => void openConversation(id)} onNew={newConversation} onClose={() => setHistoryOpen(false)} />
        <div ref={scrollRef} className="tm-well tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-xl px-4 py-6 sm:px-8">
          {messages.length === 0 && (
            <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center py-10">
              <div className="mb-6 flex items-center gap-3">
                <div className="tm-orb grid size-11 place-items-center rounded-xl"><Sparkles className="size-4 text-cyan-200"/></div>
                <Badge className="w-fit border-cyan-300/15 text-cyan-300"><GitBranch className="size-3" /> inspectable by design</Badge>
              </div>
              <h2 className="max-w-2xl text-3xl font-semibold tracking-[-.035em] text-slate-100 sm:text-[42px] sm:leading-[1.08]">Ask the ecosystem.<br/><span className="tm-gradient-text">See exactly why it answered.</span></h2>
              <p className="mt-5 max-w-2xl text-sm leading-7 text-slate-500">Architecture, SDK, EDC, Digital Twin Registry, semantic models, releases and debugging — routed, retrieved, reranked and cited against immutable source.</p>
              <div className="mt-7 flex flex-wrap gap-2">
                {["6 source families", "hybrid retrieval", "claim verification", "commit-pinned provenance"].map((item) => <span key={item} className="tm-kpi-chip">{item}</span>)}
              </div>
              <div className="mt-8 grid gap-2 sm:grid-cols-2">
                {QUICK_PROMPTS.map(({ label, prompt, icon: Icon }) => (
                  <button key={prompt} onClick={() => { setQuestion(prompt); requestAnimationFrame(() => composerRef.current?.focus()); }} className="tm-prompt group rounded-xl p-3.5 text-left transition">
                    <div className="flex items-center gap-2"><Icon className="size-3.5 text-cyan-300"/><span className="tm-label text-cyan-300/70">{label}</span></div>
                    <div className="mt-2 text-xs leading-5 text-slate-400 transition group-hover:text-slate-200">{prompt}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="mx-auto max-w-3xl space-y-7">
            {messages.map((message) => message.role === "user" ? (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} key={message.id} className="ml-auto max-w-[82%] rounded-2xl rounded-br-md border border-white/7 bg-white/[.045] px-4 py-3 text-sm leading-6 text-slate-200 shadow-[0_8px_24px_rgba(0,0,0,.14)]">{message.text}</motion.div>
            ) : (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} key={message.id} className="group max-w-[96%]">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2"><span className={`tm-led ${message.historical ? "" : "cyan"}`} /><span className="tm-label">TractusMind</span>{message.payload && <span className="hidden font-mono text-[9px] text-slate-700 sm:inline">{message.payload.interaction_id ? shortSha(message.payload.interaction_id, 10) : "live"}</span>}</div>
                  {hasPayload(message) && <Button size="sm" variant="ghost" className="opacity-60 transition group-hover:opacity-100" aria-label="Copy answer" onClick={() => void copyAnswer(message)}>{copiedAnswer === message.id ? <Check className="size-3.5 text-emerald-300"/> : <Copy className="size-3.5"/>}</Button>}
                </div>
                {message.payload ? <AnswerBody payload={message.payload} onCitation={setSelectedCitation} /> : <HistoricalAnswer text={message.text} />}
                {message.payload && <div className="mt-3 flex items-center gap-1"><span className="mr-1 text-[9px] uppercase tracking-[.12em] text-slate-700">signal</span><Button size="sm" variant="ghost" aria-label="Useful answer" onClick={() => void rate(message.payload!, "up")} className={feedback[message.payload.interaction_id ?? ""] === "up" ? "text-emerald-300" : ""}><ThumbsUp className="size-3.5" /></Button><Button size="sm" variant="ghost" aria-label="Poor answer" onClick={() => void rate(message.payload!, "down")} className={feedback[message.payload.interaction_id ?? ""] === "down" ? "text-red-300" : ""}><ThumbsDown className="size-3.5" /></Button></div>}
              </motion.div>
            ))}
            {pending && <ProcessingRail />}
            {error && <motion.div initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-red-300/15 bg-red-300/5 px-4 py-3 text-sm text-red-200"><div className="flex items-center justify-between gap-3"><span>{error}</span>{lastFailedQuestion && <Button size="sm" variant="ghost" disabled={pending} onClick={() => void send(lastFailedQuestion)}><RotateCw className="size-3.5"/>Retry</Button>}</div></motion.div>}
          </div>
        </div>
        <div className="tm-composer mt-3 rounded-2xl p-2">
          <div className="flex items-end gap-2">
            <textarea ref={composerRef} value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="Ask TractusMind…  use ref: or commit: for a pinned answer" rows={2} className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600" />
            <Button variant="primary" size="icon" disabled={!question.trim() || pending} onClick={() => void send()} aria-label="Send question"><ArrowUp className="size-4" /></Button>
          </div>
          <div className="flex items-center justify-between gap-3 px-3 pb-1 pt-1.5">
            <div className="flex min-w-0 items-center gap-3 font-mono text-[9px] text-slate-700">{conversationId ? <span className="truncate">session {shortSha(conversationId, 12)}</span> : <span>new grounded session</span>}</div>
            <div className="hidden items-center gap-3 text-[9px] text-slate-700 sm:flex"><span className="flex items-center gap-1"><CornerDownLeft className="size-3"/>send</span><span>shift + enter newline</span><span>⌘/ctrl K focus</span></div>
          </div>
        </div>
      </section>
      <Inspector citation={selectedCitation} answer={latestAnswer} />
      <MobileInspector citation={selectedCitation} onClose={() => setSelectedCitation(null)} />
    </div>
  );
}
