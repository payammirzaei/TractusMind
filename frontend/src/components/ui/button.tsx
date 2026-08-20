import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "tm-control inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold outline-none disabled:pointer-events-none disabled:opacity-45 focus-visible:ring-2 focus-visible:ring-cyan-300/40",
  {
    variants: {
      variant: {
        default: "text-slate-100",
        primary: "border-cyan-300/20 bg-[linear-gradient(180deg,#17424c,#102a31)] text-cyan-100 shadow-[0_5px_14px_rgba(0,0,0,.45),inset_0_1px_0_rgba(145,241,255,.18)]",
        danger: "border-red-300/20 text-red-200",
        ghost: "border-transparent bg-transparent shadow-none hover:bg-white/5",
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
