"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

type ActivityPayload = {
  event_type: "page_view" | "click";
  session_id: string;
  visitor_id: string;
  path: string;
  referrer?: string | null;
  target?: string | null;
  metadata?: Record<string, string | number | boolean | null>;
};

function stableId(storage: Storage, key: string) {
  const existing = storage.getItem(key);
  if (existing) return existing;
  const value = crypto.randomUUID();
  storage.setItem(key, value);
  return value;
}

function ids() {
  try {
    return {
      session_id: stableId(window.sessionStorage, "tm_activity_session"),
      visitor_id: stableId(window.localStorage, "tm_activity_visitor"),
    };
  } catch {
    return {
      session_id: crypto.randomUUID(),
      visitor_id: crypto.randomUUID(),
    };
  }
}

function send(payload: ActivityPayload) {
  void fetch("/api/backend/v1/activity/events", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
    keepalive: true,
  }).catch(() => undefined);
}

function readableTarget(element: HTMLElement) {
  const explicit = element.dataset.track?.trim();
  if (explicit) return explicit.slice(0, 512);
  const aria = element.getAttribute("aria-label")?.trim();
  if (aria) return aria.slice(0, 512);
  const title = element.getAttribute("title")?.trim();
  if (title) return title.slice(0, 512);
  const text = element.textContent?.replace(/\s+/g, " ").trim();
  return (text || element.tagName.toLowerCase()).slice(0, 512);
}

export function ActivityTracker() {
  const pathname = usePathname();

  useEffect(() => {
    const identity = ids();
    send({
      event_type: "page_view",
      ...identity,
      path: pathname || window.location.pathname,
      referrer: document.referrer || null,
      metadata: { title: document.title.slice(0, 256) },
    });
  }, [pathname]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      const source = event.target instanceof Element ? event.target : null;
      const clickable = source?.closest<HTMLElement>("a,button,[role='button']");
      if (!clickable || clickable.closest("[data-track-ignore]")) return;

      const identity = ids();
      const metadata: Record<string, string> = {
        tag: clickable.tagName.toLowerCase(),
      };
      if (clickable instanceof HTMLAnchorElement) {
        const href = clickable.getAttribute("href");
        if (href && !href.toLowerCase().startsWith("javascript:")) {
          metadata.href = href.slice(0, 256);
        }
      }

      send({
        event_type: "click",
        ...identity,
        path: window.location.pathname,
        target: readableTarget(clickable),
        metadata,
      });
    }

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  return null;
}
