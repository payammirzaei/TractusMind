import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

export type OIDCDiscovery = {
  authorization_endpoint: string;
  token_endpoint: string;
};

export const OIDC_TRANSACTION_MAX_AGE_SECONDS = 10 * 60;

const production = process.env.NODE_ENV === "production";
const cookiePrefix = production ? "__Host-" : "";

export const OIDC_STATE_COOKIE = `${cookiePrefix}tm_oidc_state`;
export const OIDC_VERIFIER_COOKIE = `${cookiePrefix}tm_oidc_verifier`;
export const OIDC_RETURN_COOKIE = `${cookiePrefix}tm_oidc_return`;

export const OIDC_TRANSACTION_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: production,
  sameSite: "lax" as const,
  path: "/",
  maxAge: OIDC_TRANSACTION_MAX_AGE_SECONDS,
};

export type OIDCServerConfig = {
  enabled: boolean;
  issuerUrl: string;
  clientId: string;
  scopes: string;
  redirectUri?: string;
};

let cachedDiscovery: { issuer: string; expiresAt: number; value: OIDCDiscovery } | null = null;

function enabledFlag(value: string | undefined) {
  return ["1", "true", "yes", "on"].includes((value ?? "").trim().toLowerCase());
}

export function oidcConfig(): OIDCServerConfig {
  const issuerUrl = (process.env.TRACTUSMIND_OIDC_ISSUER_URL ?? "").trim().replace(/\/$/, "");
  const clientId = (process.env.TRACTUSMIND_OIDC_CLIENT_ID ?? "").trim();
  const explicitlyEnabled = enabledFlag(process.env.TRACTUSMIND_OIDC_ENABLED);
  return {
    enabled: explicitlyEnabled && Boolean(issuerUrl && clientId),
    issuerUrl,
    clientId,
    scopes: (process.env.TRACTUSMIND_OIDC_SCOPES ?? "openid profile email").trim() || "openid profile email",
    redirectUri: (process.env.TRACTUSMIND_OIDC_REDIRECT_URI ?? "").trim() || undefined,
  };
}

export function redirectUriFor(request: Request, configured?: string) {
  if (configured) return configured;
  const forwardedProto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const host = forwardedHost || request.headers.get("host");
  if (host) {
    const protocol = forwardedProto || new URL(request.url).protocol.replace(":", "") || "https";
    return `${protocol}://${host}/api/oidc/callback`;
  }
  return new URL("/api/oidc/callback", request.url).toString();
}

export function safeReturnTo(value: string | null | undefined) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }
  return value;
}

export function randomBase64Url(bytes = 32) {
  return randomBytes(bytes).toString("base64url");
}

export function pkceChallenge(verifier: string) {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function secureEqual(left: string, right: string) {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function oidcDiscovery(config = oidcConfig()): Promise<OIDCDiscovery> {
  if (!config.enabled) throw new Error("OIDC login is not configured");
  const now = Date.now();
  if (cachedDiscovery && cachedDiscovery.issuer === config.issuerUrl && cachedDiscovery.expiresAt > now) {
    return cachedDiscovery.value;
  }

  const response = await fetch(`${config.issuerUrl}/.well-known/openid-configuration`, {
    headers: { accept: "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`OIDC discovery failed: ${response.status}`);
  const payload = await response.json() as Partial<OIDCDiscovery>;
  if (!payload.authorization_endpoint || !payload.token_endpoint) {
    throw new Error("OIDC discovery is missing authorization/token endpoints");
  }
  const value = {
    authorization_endpoint: payload.authorization_endpoint,
    token_endpoint: payload.token_endpoint,
  };
  cachedDiscovery = { issuer: config.issuerUrl, expiresAt: now + 5 * 60_000, value };
  return value;
}
