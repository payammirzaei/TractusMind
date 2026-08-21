import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_OPTIONS,
  SESSION_MAX_AGE_SECONDS,
  trustedBrowserMutation,
} from "@/lib/server-session";

const API_URL = (process.env.TRACTUSMIND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const UPSTREAM_TIMEOUT_MS = 15_000;

function noStore(response: NextResponse) {
  response.headers.set("cache-control", "no-store, max-age=0");
  return response;
}

function expireSession(response: NextResponse) {
  response.cookies.set(SESSION_COOKIE_NAME, "", {
    ...SESSION_COOKIE_OPTIONS,
    maxAge: 0,
  });
  return response;
}

async function identityFor(token: string) {
  return fetch(`${API_URL}/v1/me`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
}

export async function GET() {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE_NAME)?.value;
  if (!token) {
    return noStore(NextResponse.json({ detail: "Not authenticated" }, { status: 401 }));
  }

  try {
    const response = await identityFor(token);
    const body = await response.text();
    const nextResponse = noStore(
      new NextResponse(body, {
        status: response.status,
        headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
      }),
    );
    if (response.status === 401 || response.status === 403) expireSession(nextResponse);
    return nextResponse;
  } catch {
    return noStore(NextResponse.json({ detail: "TractusMind API unavailable" }, { status: 503 }));
  }
}

export async function POST(request: Request) {
  if (!trustedBrowserMutation(request)) {
    return noStore(
      NextResponse.json({ detail: "Cross-site session mutation rejected" }, { status: 403 }),
    );
  }

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return noStore(NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 }));
  }

  const username =
    typeof payload === "object" &&
    payload !== null &&
    "username" in payload &&
    typeof payload.username === "string"
      ? payload.username.trim()
      : "";
  const password =
    typeof payload === "object" &&
    payload !== null &&
    "password" in payload &&
    typeof payload.password === "string"
      ? payload.password
      : "";

  if (!username || username.length > 80 || !password || password.length > 1024) {
    return noStore(
      NextResponse.json({ detail: "Username and password are required" }, { status: 422 }),
    );
  }

  try {
    const upstream = await fetch(`${API_URL}/v1/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const body = await upstream.text();
    if (!upstream.ok) {
      return noStore(
        new NextResponse(body, {
          status: upstream.status,
          headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
        }),
      );
    }

    let authenticated: Record<string, unknown>;
    try {
      authenticated = JSON.parse(body) as Record<string, unknown>;
    } catch {
      return noStore(NextResponse.json({ detail: "Invalid authentication response" }, { status: 502 }));
    }
    const token = typeof authenticated.token === "string" ? authenticated.token : "";
    if (!token || token.length > 4096) {
      return noStore(NextResponse.json({ detail: "Invalid authentication response" }, { status: 502 }));
    }

    const expiresIn =
      typeof authenticated.expires_in === "number" && authenticated.expires_in > 0
        ? Math.min(authenticated.expires_in, SESSION_MAX_AGE_SECONDS)
        : SESSION_MAX_AGE_SECONDS;
    const { token: _token, expires_in: _expiresIn, ...identity } = authenticated;
    void _token;
    void _expiresIn;

    const response = noStore(NextResponse.json(identity));
    response.cookies.set(SESSION_COOKIE_NAME, token, {
      ...SESSION_COOKIE_OPTIONS,
      maxAge: expiresIn,
    });
    return response;
  } catch {
    return noStore(NextResponse.json({ detail: "TractusMind API unavailable" }, { status: 503 }));
  }
}

export async function DELETE(request: Request) {
  if (!trustedBrowserMutation(request)) {
    return noStore(
      NextResponse.json({ detail: "Cross-site session mutation rejected" }, { status: 403 }),
    );
  }

  return noStore(expireSession(NextResponse.json({ ok: true })));
}
