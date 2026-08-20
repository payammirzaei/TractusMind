import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: ComponentProps<"span">) {
  return (
    <span
      data-slot="badge"
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-white/8 bg-black/20 px-2 py-1 text-[10px] font-bold uppercase tracking-[.12em] text-slate-400",
        className,
      )}
      {...props}
    />
  );
}
