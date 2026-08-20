import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_OPTIONS,
  SESSION_MAX_AGE_SECONDS,
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

function trustedBrowserMutation(request: Request) {
  const requestUrl = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite === "cross-site") return false;
  return !origin || origin === requestUrl.origin;
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

  const token =
    typeof payload === "object" &&
    payload !== null &&
    "token" in payload &&
    typeof payload.token === "string"
      ? payload.token.trim()
      : "";
  if (!token || token.length > 8192) {
    return noStore(
      NextResponse.json({ detail: "A valid bearer credential is required" }, { status: 422 }),
    );
  }

  try {
    const upstream = await identityFor(token);
    const body = await upstream.text();
    if (!upstream.ok) {
      return noStore(
        new NextResponse(body, {
          status: upstream.status,
          headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
        }),
      );
    }

    const response = noStore(
      new NextResponse(body, {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    response.cookies.set(SESSION_COOKIE_NAME, token, {
      ...SESSION_COOKIE_OPTIONS,
      maxAge: SESSION_MAX_AGE_SECONDS,
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
