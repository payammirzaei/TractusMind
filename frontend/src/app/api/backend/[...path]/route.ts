import { cookies } from "next/headers";

const COOKIE = "tm_session";
const API_URL = (process.env.TRACTUSMIND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const ALLOWED_ROOTS = new Set(["v1", "health"]);

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context) {
  const { path } = await context.params;
  if (!path.length || !ALLOWED_ROOTS.has(path[0]) || path.some((part) => part === ".." || part.includes("\\"))) {
    return Response.json({ detail: "Unsupported backend path" }, { status: 404 });
  }

  const incoming = new URL(request.url);
  const target = `${API_URL}/${path.map(encodeURIComponent).join("/")}${incoming.search}`;
  const store = await cookies();
  const token = store.get(COOKIE)?.value;
  const headers = new Headers();
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (token) headers.set("authorization", `Bearer ${token}`);

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "x-request-id", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "TractusMind API unavailable" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
