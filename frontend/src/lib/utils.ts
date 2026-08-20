import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function shortSha(value?: string | null, length = 8) {
  return value ? value.slice(0, length) : "—";
}

export function formatDate(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function percent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}
