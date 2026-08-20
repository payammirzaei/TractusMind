"use client";

import { useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowUp,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  GitBranch,
  Search,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AnswerCitation, GroundedAnswer } from "@/lib/types";
import { shortSha } from "@/lib/utils";

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string; payload: GroundedAnswer };

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
              className="mx-1 inline-flex translate-y-[-1px] rounded-md border border-cyan-300/20 bg-cyan-300/8 px-1.5 py-0.5 font-mono text-[10px] font-bold text-cyan-200 hover:bg-cyan-300/15"
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
        {payload.model && <Badge>{payload.model}</Badge>}
      </div>
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
    <aside className="tm-panel tm-desktop-only flex min-h-0 w-[360px] shrink-0 flex-col rounded-2xl p-3">
      <div className="mb-3 flex items-center justify-between px-1">
        <div><div className="tm-label">Evidence inspector</div><div className="mt-1 text-sm font-semibold">Provenance channel</div></div>
        <div className="flex items-center gap-2"><span className="tm-led cyan" /><span className="tm-label">live</span></div>
      </div>
      <div className="tm-well tm-scanline flex min-h-0 flex-1 flex-col rounded-xl p-4">
        {!citation ? (
          <div className="m-auto max-w-[240px] text-center">
            <Search className="mx-auto mb-3 size-6 text-slate-600" />
            <div className="text-sm font-semibold text-slate-300">Select a source marker</div>
            <p className="mt-2 text-xs leading-5 text-slate-600">Every answer citation opens its immutable repository, commit, file, line range and retrieval trace here.</p>
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
                  {answer.route.reasons.map((reason) => <div key={reason} className="rounded-md bg-white/[.025] px-2 py-1.5 font-mono text-[10px]">{reason}</div>)}
                </div>
              </div>
            )}
            {answer?.verification && (
              <div className="border-t border-white/5 pt-4">
                <div className="mb-2 flex items-center gap-2"><CheckCircle2 className={answer.verification.passed ? "size-4 text-emerald-300" : "size-4 text-red-300"} /><span className="text-xs font-semibold">Claim verification {answer.verification.passed ? "passed" : "failed"}</span></div>
                <div className="text-[11px] text-slate-500">{answer.verification.claims.length} atomic claims · {answer.verification.unsupported_claim_count} unsupported</div>
              </div>
            )}
            <div className="flex gap-2">
              <Button size="sm" className="flex-1" onClick={async () => { await navigator.clipboard.writeText(`${citation.repository}@${citation.commit_sha}:${citation.path}#L${citation.start_line}-L${citation.end_line}`); setCopied(true); setTimeout(() => setCopied(false), 1200); }}>
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? "Copied" : "Copy ref"}
              </Button>
              <a className="tm-control inline-flex size-8 items-center justify-center rounded-lg" href={citation.source_url} target="_blank" rel="noreferrer"><ExternalLink className="size-3.5" /></a>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

export function ChatWorkbench() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<AnswerCitation | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "up" | "down">>({});
  const latestAnswer = useMemo(() => [...messages].reverse().find((item) => item.role === "assistant")?.payload ?? null, [messages]);

  async function send() {
    const value = question.trim();
    if (!value || pending) return;
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", text: value };
    setMessages((current) => [...current, userMessage]);
    setQuestion(""); setPending(true); setError(null);
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
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to reach TractusMind");
    } finally { setPending(false); }
  }

  async function rate(answer: GroundedAnswer, rating: "up" | "down") {
    if (!answer.interaction_id) return;
    const response = await fetch("/api/backend/v1/feedback", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ interaction_id: answer.interaction_id, rating }),
    });
    if (response.ok) setFeedback((current) => ({ ...current, [answer.interaction_id!]: rating }));
  }

  return (
    <div className="flex min-h-0 flex-1 gap-3">
      <section className="tm-panel flex min-w-0 flex-1 flex-col rounded-2xl p-3">
        <div className="mb-3 flex items-center justify-between px-1">
          <div><div className="tm-label">AI engineering copilot</div><h1 className="mt-1 text-base font-semibold tracking-tight">Grounded workbench</h1></div>
          <div className="hidden items-center gap-2 sm:flex"><span className="tm-led" /><span className="tm-label">evidence guard armed</span></div>
        </div>
        <div className="tm-well tm-scrollbar min-h-0 flex-1 overflow-y-auto rounded-xl px-4 py-6 sm:px-8">
          {messages.length === 0 && (
            <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center py-12">
              <Badge className="mb-5 w-fit border-cyan-300/15 text-cyan-300"><GitBranch className="size-3" /> inspectable by design</Badge>
              <h2 className="text-3xl font-semibold tracking-[-.03em] text-slate-100 sm:text-4xl">Ask the ecosystem.<br/><span className="text-slate-500">See exactly why it answered.</span></h2>
              <p className="mt-5 max-w-xl text-sm leading-7 text-slate-500">Architecture, SDK, EDC, Digital Twin Registry, semantic models, releases and debugging — routed, retrieved, reranked and cited against versioned source.</p>
              <div className="mt-7 grid gap-2 sm:grid-cols-2">
                {["Why would an EDC transfer process stay in REQUESTED?", "Show the SDK APIs involved in policy negotiation", "Which semantic-model files define the relevant aspect?", "Compare this behavior across a pinned ref"].map((prompt) => (
                  <button key={prompt} onClick={() => setQuestion(prompt)} className="tm-panel rounded-xl p-3 text-left text-xs leading-5 text-slate-400 transition hover:border-cyan-300/15 hover:text-slate-200">{prompt}</button>
                ))}
              </div>
            </div>
          )}
          <div className="mx-auto max-w-3xl space-y-7">
            {messages.map((message) => message.role === "user" ? (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} key={message.id} className="ml-auto max-w-[78%] rounded-2xl rounded-br-md border border-white/7 bg-white/[.045] px-4 py-3 text-sm leading-6 text-slate-200">{message.text}</motion.div>
            ) : (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} key={message.id} className="max-w-[94%]">
                <div className="mb-2 flex items-center gap-2"><span className="tm-led cyan" /><span className="tm-label">TractusMind</span></div>
                <AnswerBody payload={message.payload} onCitation={setSelectedCitation} />
                <div className="mt-3 flex gap-1">
                  <Button size="sm" variant="ghost" aria-label="Useful answer" onClick={() => rate(message.payload, "up")} className={feedback[message.payload.interaction_id ?? ""] === "up" ? "text-emerald-300" : ""}><ThumbsUp className="size-3.5" /></Button>
                  <Button size="sm" variant="ghost" aria-label="Poor answer" onClick={() => rate(message.payload, "down")} className={feedback[message.payload.interaction_id ?? ""] === "down" ? "text-red-300" : ""}><ThumbsDown className="size-3.5" /></Button>
                </div>
              </motion.div>
            ))}
            {pending && <div className="flex items-center gap-3 text-xs text-slate-500"><div className="tm-thinking flex gap-1"><span className="tm-led cyan"/><span className="tm-led cyan"/><span className="tm-led cyan"/></div> routing → retrieving → reranking → verifying</div>}
            {error && <div className="rounded-xl border border-red-300/15 bg-red-300/5 px-4 py-3 text-sm text-red-200">{error}</div>}
          </div>
        </div>
        <div className="mt-3 rounded-2xl border border-white/7 bg-black/20 p-2 shadow-[inset_0_2px_8px_rgba(0,0,0,.55)]">
          <div className="flex items-end gap-2">
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="Ask TractusMind…  try ref: or commit: for a pinned answer" rows={2} className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600" />
            <Button variant="primary" size="icon" disabled={!question.trim() || pending} onClick={() => void send()}><ArrowUp className="size-4" /></Button>
          </div>
        </div>
      </section>
      <Inspector citation={selectedCitation} answer={latestAnswer ?? null} />
    </div>
  );
}
