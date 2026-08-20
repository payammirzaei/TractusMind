import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const COOKIE = "tm_session";
const API_URL = (process.env.TRACTUSMIND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function identityFor(token: string) {
  const response = await fetch(`${API_URL}/v1/me`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    cache: "no-store",
  });
  return response;
}

export async function GET() {
  const store = await cookies();
  const token = store.get(COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });

  try {
    const response = await identityFor(token);
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "TractusMind API unavailable" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const payload = (await request.json()) as { token?: string };
  const token = payload.token?.trim();
  if (!token || token.length > 8192) {
    return NextResponse.json({ detail: "A valid bearer credential is required" }, { status: 422 });
  }

  try {
    const upstream = await identityFor(token);
    const body = await upstream.text();
    if (!upstream.ok) {
      return new NextResponse(body, {
        status: upstream.status,
        headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
      });
    }

    const response = new NextResponse(body, {
      status: 200,
      headers: { "content-type": "application/json" },
    });
    response.cookies.set(COOKIE, token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 8,
    });
    return response;
  } catch {
    return NextResponse.json({ detail: "TractusMind API unavailable" }, { status: 503 });
  }
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}
