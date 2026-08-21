# Mission Control UI

TractusMind Mission Control is the Next.js control surface for the source-grounded backend.

## Stack

- Next.js 16.3 + React 19.2
- Tailwind CSS 4.3
- shadcn-compatible local component layer
- Motion for tactile transitions
- Lucide icons

The visual language is modern industrial skeuomorphism: graphite chassis, recessed evidence wells,
tactile controls, status LEDs, and restrained cyan/amber instrumentation. Chat content remains
comparatively flat for readability.

## Security boundary

The browser never stores the bearer credential in localStorage. `POST /api/session` validates the
credential against backend `/v1/me` and writes an HttpOnly, Secure-in-production, SameSite=Lax
session cookie. Production uses the `__Host-` cookie prefix. Session responses are non-cacheable and
session mutations reject cross-site browser requests.

Browser API requests go through `/api/backend/*`; the Next.js server attaches the bearer credential
server-side. The BFF allows only the backend roots used by Mission Control: `/v1/ask`,
`/v1/conversations`, `/v1/feedback`, `/v1/me`, `/v1/ops/*`, and backend health endpoints. Mutating
proxy requests reject cross-site browser requests, request bodies are capped at 1 MiB, redirects are
not followed, and upstream calls have bounded timeouts.

Baseline browser security headers are configured in `next.config.ts`. HTML/document responses receive
a per-request nonce CSP from `frontend/src/proxy.ts`; production script execution requires the nonce
and `strict-dynamic` rather than `unsafe-inline`. Caddy preserves that application CSP and adds the
edge-only HSTS policy while repeating the remaining defensive headers. The policy denies framing,
objects, cross-origin application connections, browser camera/microphone/geolocation access, DNS
prefetching, and referrer leakage. CI probes the built production runtime and asserts the nonce CSP,
`strict-dynamic`, framing policy, connection policy, and baseline security headers.

## Enterprise SSO

Mission Control supports optional OIDC Authorization Code + PKCE login for a **public browser client**.
No OIDC client secret is stored in the frontend or sent to the browser.

```text
Mission Control
  -> /api/oidc/login
  -> OIDC discovery
  -> authorization endpoint + state + PKCE S256 challenge
  -> /api/oidc/callback
  -> server-side code exchange + PKCE verifier
  -> access token
  -> backend /v1/me validation
  -> existing HttpOnly Mission Control session
```

The temporary state, PKCE verifier, and safe return path live only in short-lived HttpOnly cookies.
State comparison is timing-safe. Return targets are restricted to local absolute paths to prevent
open redirects. The callback validates the returned access token through the backend before creating
a session, so backend OIDC signature/audience/issuer/RBAC policy remains authoritative.

Configure the IdP client as Authorization Code + PKCE with no client secret. Frontend runtime values:

```text
TRACTUSMIND_OIDC_ENABLED=false
TRACTUSMIND_OIDC_ISSUER_URL
TRACTUSMIND_OIDC_CLIENT_ID
TRACTUSMIND_OIDC_SCOPES
TRACTUSMIND_OIDC_REDIRECT_URI   # recommended explicitly in production
```

Browser SSO is enabled only when the explicit enable flag is truthy and issuer/client ID are present.
The Compose topology maps `TRACTUSMIND_OIDC_ENABLED` from the root `OIDC_ENABLED` value so frontend
SSO cannot silently diverge from backend OIDC validation.

Backend OIDC validation continues to use `OIDC_ENABLED`, `OIDC_ISSUER_URL`, `OIDC_AUDIENCE`, role
claims, allowed algorithms, and configured operator/admin roles.

## Functional consoles

- `/` — grounded chat, citation markers, route/verification metadata, feedback, conversation history
- `/overview` — live Command Center: core health, source coverage, ingestion activity, quality guard,
  topology, and active identity authority
- `/sources` — searchable source registry, snapshot commits, drill-down state, admin sync action
- `/ops` — live ingestion summary, filters, run channel, and run inspector
- `/quality` — searchable human review queue, review inspector, decisions, and regression status
- `/admin` — identity search/filter, API-key provisioning/rotation, roles, and enable/disable controls

Navigation is role-aware: users see Copilot, operators gain Overview/Sources/Ops/Quality, admins gain
Access. Backend RBAC remains authoritative even if a client bypasses UI navigation.

`Ctrl/Command + K` opens the global Mission Control launcher.

## Resilience

Mission Control includes dedicated route loading, themed 404, recoverable surface error, and
root-level fail-safe surfaces. A degraded backend readiness response is displayed as degraded health
rather than crashing the Command Center.

Mission Control exposes a lightweight frontend liveness route:

```text
GET /api/health
```

The production container healthcheck and Caddy active health probe both use this route rather than
rendering the full workbench page. The sidebar and Command Center separately consume backend
`/health/ready` for PostgreSQL, Redis, and Qdrant readiness.

## Local development

Run the backend stack plus the UI overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.ui.yml up --build
```

Mission Control is served at `http://localhost:3100`. Grafana keeps `http://localhost:3000`.

Or run the frontend directly:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

## Production

Use the hardened backend compose plus the UI overlay:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.ui.prod.yml \
  up -d --build
```

The UI overlay replaces Caddy's upstream with the frontend container. The frontend talks to the API
only over the private backend network. Caddy remains the sole public edge on 443.

For SSO, register the exact production callback, for example:

```text
https://tractusmind.example.com/api/oidc/callback
```

## Validation

`.github/workflows/frontend.yml` now runs:

1. production dependency audit at HIGH severity,
2. TypeScript typecheck,
3. Next.js production build,
4. production Next runtime route + nonce-CSP/browser-policy smoke,
5. BFF/session security integration smoke with a deterministic backend,
6. OIDC Authorization Code + PKCE integration smoke with a deterministic IdP,
7. runtime Docker image build,
8. route + BFF smoke against the actual built image,
9. development UI Compose-overlay validation,
10. production UI Compose-overlay validation.

The BFF gate checks secure cookie policy, session round-trip, backend allowlisting, anonymous access,
cross-site mutation rejection, read-only health access, and Command Center API contracts. The OIDC
gate checks discovery, PKCE, state validation, code exchange, backend identity validation, and open
redirect rejection.

The hardened Production Runtime gate separately boots the real production Compose topology behind
Caddy, verifies private service exposure/read-only roots, provisions an admin identity through the
private API, performs authenticated HTTPS Mission Control smoke with certificate verification, and
tears the stack down cleanly.

The workflow pins checkout/setup-node actions to immutable commit SHAs and uses Node 24.19.0 LTS.
The repository security workflow separately builds and scans both backend and Mission Control images.
