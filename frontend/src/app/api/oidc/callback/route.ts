import { NextResponse } from "next/server";

import {
  OIDC_RETURN_COOKIE,
  OIDC_STATE_COOKIE,
  OIDC_TRANSACTION_COOKIE_OPTIONS,
  OIDC_VERIFIER_COOKIE,
  oidcConfig,
  oidcDiscovery,
  redirectUriFor,
  safeReturnTo,
  secureEqual,
} from "@/lib/server-oidc";
import {
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_OPTIONS,
  SESSION_MAX_AGE_SECONDS,
} from "@/lib/server-session";
import { cookies } from "next/headers";

const API_URL = (process.env.TRACTUSMIND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

function clearTransaction(response: NextResponse) {
  for (const name of [OIDC_STATE_COOKIE, OIDC_VERIFIER_COOKIE, OIDC_RETURN_COOKIE]) {
    response.cookies.set(name, "", { ...OIDC_TRANSACTION_COOKIE_OPTIONS, maxAge: 0 });
  }
  return response;
}

function failure(request: Request, code: string) {
  const target = new URL("/", request.url);
  target.searchParams.set("auth_error", code);
  const response = clearTransaction(NextResponse.redirect(target));
  response.headers.set("cache-control", "no-store, max-age=0");
  return response;
}

export async function GET(request: Request) {
  const config = oidcConfig();
  if (!config.enabled) return failure(request, "sso_not_configured");

  const incoming = new URL(request.url);
  if (incoming.searchParams.get("error")) return failure(request, "provider_rejected");

  const code = incoming.searchParams.get("code")?.trim() ?? "";
  const state = incoming.searchParams.get("state")?.trim() ?? "";
  const store = await cookies();
  const expectedState = store.get(OIDC_STATE_COOKIE)?.value ?? "";
  const verifier = store.get(OIDC_VERIFIER_COOKIE)?.value ?? "";
  const returnTo = safeReturnTo(store.get(OIDC_RETURN_COOKIE)?.value);

  if (!code || !state || !expectedState || !verifier || !secureEqual(state, expectedState)) {
    return failure(request, "invalid_sso_state");
  }

  try {
    const discovery = await oidcDiscovery(config);
    const redirectUri = redirectUriFor(request, config.redirectUri);
    const tokenResponse = await fetch(discovery.token_endpoint, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        client_id: config.clientId,
        redirect_uri: redirectUri,
        code_verifier: verifier,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    const tokenPayload = await tokenResponse.json() as {
      access_token?: unknown;
      expires_in?: unknown;
    };
    if (!tokenResponse.ok || typeof tokenPayload.access_token !== "string") {
      return failure(request, "token_exchange_failed");
    }

    const accessToken = tokenPayload.access_token.trim();
    if (!accessToken || accessToken.length > 8192) return failure(request, "invalid_access_token");

    const identity = await fetch(`${API_URL}/v1/me`, {
      headers: { authorization: `Bearer ${accessToken}`, accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    if (!identity.ok) return failure(request, "identity_rejected");

    const target = new URL(returnTo, request.url);
    const response = clearTransaction(NextResponse.redirect(target));
    response.headers.set("cache-control", "no-store, max-age=0");
    const expiresIn = typeof tokenPayload.expires_in === "number" && Number.isFinite(tokenPayload.expires_in)
      ? Math.max(1, Math.floor(tokenPayload.expires_in))
      : SESSION_MAX_AGE_SECONDS;
    response.cookies.set(SESSION_COOKIE_NAME, accessToken, {
      ...SESSION_COOKIE_OPTIONS,
      maxAge: Math.min(SESSION_MAX_AGE_SECONDS, expiresIn),
    });
    return response;
  } catch {
    return failure(request, "sso_unavailable");
  }
}
