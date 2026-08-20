"use client";

import Link from "next/link";
import { AlertTriangle, Home, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center p-5">
      <div className="tm-shell relative w-full max-w-[620px] rounded-[28px] p-3">
        <span className="tm-screw absolute left-4 top-4"/><span className="tm-screw absolute right-4 top-4"/><span className="tm-screw absolute bottom-4 left-4"/><span className="tm-screw absolute bottom-4 right-4"/>
        <div className="tm-well rounded-[20px] p-7 sm:p-9">
          <div className="tm-orb grid size-12 place-items-center rounded-2xl"><AlertTriangle className="size-5 text-red-300"/></div>
          <div className="tm-label mt-6 text-red-300">surface fault</div>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-.03em]">Mission Control hit a recoverable UI error.</h1>
          <p className="mt-4 max-w-xl text-sm leading-6 text-slate-500">The current surface could not render safely. Your authenticated session is kept; retry the surface or return to the grounded copilot.</p>
          <div className="mt-6 rounded-xl border border-red-300/10 bg-red-300/[.035] p-3 font-mono text-[10px] leading-5 text-red-200/70">{error.message || "Unexpected frontend error"}{error.digest ? ` · digest ${error.digest}` : ""}</div>
          <div className="mt-6 flex flex-wrap gap-2"><Button variant="primary" onClick={reset}><RotateCw className="size-4"/>Retry surface</Button><Link href="/"><Button><Home className="size-4"/>Back to Copilot</Button></Link></div>
        </div>
      </div>
    </main>
  );
}
