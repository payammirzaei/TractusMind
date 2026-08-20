import { cookies } from "next/headers";

import { SESSION_COOKIE_NAME } from "@/lib/server-session";

const API_URL = (process.env.TRACTUSMIND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const ALLOWED_V1_ROOTS = new Set(["ask", "conversations", "feedback", "me", "ops"]);
const MAX_BODY_BYTES = 1_048_576;
const UPSTREAM_TIMEOUT_MS = 120_000;

type Context = { params: Promise<{ path: string[] }> };

function supportedPath(path: string[]) {
  if (!path.length) return false;
  if (
    path.some(
      (part) => !part || part === "." || part === ".." || part.includes("/") || part.includes("\\"),
    )
  ) {
    return false;
  }
  if (path[0] === "health") return true;
  return path[0] === "v1" && path.length >= 2 && ALLOWED_V1_ROOTS.has(path[1]);
}

function trustedMutation(request: Request) {
  const method = request.method.toUpperCase();
  if (method === "GET" || method === "HEAD") return true;

  const requestUrl = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "cross-site") return false;
  return !origin || origin === requestUrl.origin;
}

function responseHeaders(upstream: Response) {
  const headers = new Headers();
  for (const name of ["content-type", "content-disposition", "x-request-id", "retry-after"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("cache-control", "no-store, max-age=0");
  return headers;
}

async function proxy(request: Request, context: Context) {
  const { path } = await context.params;
  if (!supportedPath(path)) {
    return Response.json({ detail: "Unsupported backend path" }, { status: 404 });
  }
  if (!trustedMutation(request)) {
    return Response.json({ detail: "Cross-site backend mutation rejected" }, { status: 403 });
  }

  const method = request.method.toUpperCase();
  if (path[0] === "health" && method !== "GET") {
    return Response.json({ detail: "Method not allowed" }, { status: 405 });
  }

  const declaredLength = Number(request.headers.get("content-length") ?? 0);
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) {
    return Response.json({ detail: "Request body too large" }, { status: 413 });
  }

  const incoming = new URL(request.url);
  const target = `${API_URL}/${path.map(encodeURIComponent).join("/")}${incoming.search}`;
  const store = await cookies();
  const token = store.get(SESSION_COOKIE_NAME)?.value;
  const headers = new Headers();
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (token) headers.set("authorization", `Bearer ${token}`);

  let body: ArrayBuffer | undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return Response.json({ detail: "Request body too large" }, { status: 413 });
    }
  }

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders(upstream),
    });
  } catch (cause) {
    if (cause instanceof Error && cause.name === "TimeoutError") {
      return Response.json({ detail: "TractusMind API timed out" }, { status: 504 });
    }
    return Response.json({ detail: "TractusMind API unavailable" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
