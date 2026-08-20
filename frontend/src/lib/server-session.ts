export const SESSION_COOKIE_NAME =
  process.env.NODE_ENV === "production" ? "__Host-tm_session" : "tm_session";

export const SESSION_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 8;

function firstForwardedValue(value: string | null) {
  return value?.split(",", 1)[0]?.trim() || null;
}

function canonicalRequestOrigin(request: Request) {
  const internalUrl = new URL(request.url);
  const forwardedHost = firstForwardedValue(request.headers.get("x-forwarded-host"));
  const host = forwardedHost ?? request.headers.get("host")?.trim() ?? internalUrl.host;
  const forwardedProto = firstForwardedValue(request.headers.get("x-forwarded-proto"));
  const protocol = forwardedProto ?? internalUrl.protocol.replace(/:$/, "");

  try {
    return new URL(`${protocol}://${host}`).origin;
  } catch {
    return internalUrl.origin;
  }
}

/**
 * Validate state-changing browser requests without assuming the server's internal
 * container origin is also the browser-visible origin.
 *
 * Browsers do not let JavaScript forge Sec-Fetch-Site, Host, or forwarded headers.
 * Production exposes Next only through the trusted Caddy reverse proxy, which
 * supplies the external host/protocol. Direct development traffic falls back to
 * the Host header. A browser explicitly reporting cross-site is always rejected.
 */
export function trustedBrowserMutation(request: Request) {
  const fetchSite = request.headers.get("sec-fetch-site")?.toLowerCase();
  if (fetchSite === "cross-site") return false;

  const origin = request.headers.get("origin");
  if (!origin) return true;

  try {
    return new URL(origin).origin === canonicalRequestOrigin(request);
  } catch {
    return false;
  }
}
