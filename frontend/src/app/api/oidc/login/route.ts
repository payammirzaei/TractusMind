import { NextResponse } from "next/server";

import {
  OIDC_RETURN_COOKIE,
  OIDC_STATE_COOKIE,
  OIDC_TRANSACTION_COOKIE_OPTIONS,
  OIDC_VERIFIER_COOKIE,
  oidcConfig,
  oidcDiscovery,
  pkceChallenge,
  randomBase64Url,
  redirectUriFor,
  safeReturnTo,
} from "@/lib/server-oidc";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function errorRedirect(request: Request, code: string) {
  const target = new URL("/", request.url);
  target.searchParams.set("auth_error", code);
  const response = NextResponse.redirect(target);
  response.headers.set("cache-control", "no-store, max-age=0");
  return response;
}

export async function GET(request: Request) {
  const config = oidcConfig();
  if (!config.enabled) return errorRedirect(request, "sso_not_configured");

  try {
    const discovery = await oidcDiscovery(config);
    const state = randomBase64Url(24);
    const verifier = randomBase64Url(48);
    const returnTo = safeReturnTo(new URL(request.url).searchParams.get("return_to"));
    const redirectUri = redirectUriFor(request, config.redirectUri);

    const authorization = new URL(discovery.authorization_endpoint);
    authorization.searchParams.set("response_type", "code");
    authorization.searchParams.set("client_id", config.clientId);
    authorization.searchParams.set("redirect_uri", redirectUri);
    authorization.searchParams.set("scope", config.scopes);
    authorization.searchParams.set("state", state);
    authorization.searchParams.set("code_challenge", pkceChallenge(verifier));
    authorization.searchParams.set("code_challenge_method", "S256");

    const response = NextResponse.redirect(authorization);
    response.headers.set("cache-control", "no-store, max-age=0");
    response.cookies.set(OIDC_STATE_COOKIE, state, OIDC_TRANSACTION_COOKIE_OPTIONS);
    response.cookies.set(OIDC_VERIFIER_COOKIE, verifier, OIDC_TRANSACTION_COOKIE_OPTIONS);
    response.cookies.set(OIDC_RETURN_COOKIE, returnTo, OIDC_TRANSACTION_COOKIE_OPTIONS);
    return response;
  } catch {
    return errorRedirect(request, "sso_unavailable");
  }
}
