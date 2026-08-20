import Link from "next/link";
import { ArrowLeft, SearchCode } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center p-5">
      <div className="tm-shell relative w-full max-w-[560px] rounded-[28px] p-3">
        <span className="tm-screw absolute left-4 top-4"/><span className="tm-screw absolute right-4 top-4"/><span className="tm-screw absolute bottom-4 left-4"/><span className="tm-screw absolute bottom-4 right-4"/>
        <div className="tm-well rounded-[20px] p-8 text-center sm:p-10">
          <div className="tm-orb mx-auto grid size-14 place-items-center rounded-2xl"><SearchCode className="size-6 text-cyan-200"/></div>
          <div className="tm-label mt-6">404 · unknown surface</div>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-.03em]">This Mission Control route does not exist.</h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-slate-500">The requested console is not registered in the current frontend build.</p>
          <Link href="/" className="mt-6 inline-block"><Button variant="primary"><ArrowLeft className="size-4"/>Return to Copilot</Button></Link>
        </div>
      </div>
    </main>
  );
}
