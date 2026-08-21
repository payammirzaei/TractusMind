import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "tm-control inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold tracking-[-.01em] outline-none disabled:pointer-events-none disabled:opacity-45 focus-visible:ring-2 focus-visible:ring-cyan-300/40",
  {
    variants: {
      variant: {
        default: "text-slate-100",
        primary: "border-cyan-300/25 bg-[linear-gradient(180deg,#1b4d59,#12313a_58%,#0c242b)] text-cyan-50 shadow-[0_7px_18px_rgba(0,0,0,.46),inset_0_1px_0_rgba(173,246,255,.2),0_0_22px_rgba(32,200,234,.035)]",
        danger: "border-red-300/20 bg-[linear-gradient(180deg,rgba(80,27,31,.52),rgba(35,14,17,.52))] text-red-200",
        ghost: "border-transparent bg-transparent shadow-none hover:border-white/5 hover:bg-white/[.045]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        default: "h-10 px-4",
        lg: "h-12 px-5",
        icon: "size-10 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({ className, variant, size, ...props }: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return <button data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
