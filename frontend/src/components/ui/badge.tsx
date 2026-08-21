import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="badge"
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-lg border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,.035),rgba(0,0,0,.18))] px-2.5 py-1 text-[9px] font-bold uppercase tracking-[.13em] text-slate-400 shadow-[inset_0_1px_0_rgba(255,255,255,.035),0_3px_10px_rgba(0,0,0,.12)]",
        className,
      )}
      {...props}
    />
  );
}
