# 04 — Authentication, Conversations, Feedback and Quality

## Why these systems were added

A source-grounded answer is not enough for a production engineering copilot. We also needed to know:

- who is asking,
- which conversation belongs to whom,
- who may operate or administer the system,
- how feedback becomes actionable quality data,
- how external enterprise identity maps into application roles.

These concerns were implemented as first-class backend capabilities rather than UI-only restrictions.

## API-key identity model

The backend supports local API-key identities with application roles:

```text
user < operator < admin
```

Local identities can be provisioned, enabled/disabled, rotated and assigned roles through operator/admin tooling.

Credentials are treated as secrets. Mission Control never persists bearer credentials in browser local storage.

## Enterprise OIDC

OIDC access-token validation was added to the backend with configurable:

- issuer URL,
- API audience,
- allowed signing algorithms,
- role-claim locations,
- admin/operator role mappings,
- display-name claims,
- cache and HTTP timeouts.

This allows an external IdP such as Keycloak or Microsoft Entra ID to remain the source of enterprise identity while TractusMind maps validated claims into its own role hierarchy.

## Mission Control SSO

The browser SSO flow uses Authorization Code + PKCE as a **public client**. No frontend client secret is required or accepted.

Flow:

```text
Mission Control
  -> /api/oidc/login
  -> provider discovery
  -> authorization endpoint
  -> state + PKCE S256 challenge
  -> /api/oidc/callback
  -> server-side token exchange
  -> backend /v1/me validation
  -> HttpOnly Mission Control session
```

Temporary OIDC cookies store only bounded transient state such as the verifier/return path and are HttpOnly, SameSite=Lax and Secure in production.

The return URL is restricted to local absolute paths so the SSO callback cannot be turned into an open redirect.

## BFF session boundary

Mission Control introduced a Backend-for-Frontend boundary:

- browser submits a bearer/API credential to `/api/session`,
- the server validates it against backend `/v1/me`,
- the browser receives an HttpOnly session cookie,
- subsequent browser calls use same-origin BFF routes,
- the raw credential is not stored in localStorage.

Production uses the `__Host-` cookie prefix and Secure/Path requirements.

Rejected/revoked backend sessions are expired immediately when a 401/403 is returned.

## Session revalidation

Mission Control does not assume a login remains valid forever.

The active session is revalidated:

- periodically,
- when the browser regains focus.

Behavior:

- 401/403 => clear local identity and return to login,
- role change for the same user => refresh role-aware UI,
- transient backend/network problem => do not force a misleading logout.

## BFF hardening

The backend proxy only allows known route roots/methods and includes:

- bounded timeout,
- bounded request body,
- redirect refusal,
- health read-only behavior,
- same-origin mutation checks,
- session rejection handling.

A later full-stack test exposed an important reverse-proxy origin issue: comparing browser `Origin` directly against an internal container request URL rejected valid requests. We replaced that with canonical external-origin handling from forwarded host/proto while keeping explicit `Sec-Fetch-Site: cross-site` rejection.

## Conversation ownership

Conversations and messages are persisted in PostgreSQL and tied to the authenticated identity.

Important invariant:

> Conversation history may influence interpretation, but it does not become retrieval evidence.

This prevents a previous assistant hallucination from becoming a self-reinforcing citation source in a later turn.

Historical provenance is also handled conservatively. Mission Control does not invent/reconstruct citation metadata for an old turn when the exact original provenance is unavailable.

## Feedback loop

Users can submit feedback on answers. Feedback is persisted and surfaced into an operator quality workflow.

The quality review model supports structured information such as:

- status,
- root-cause category,
- review kind,
- notes,
- expected source IDs,
- expected terms,
- expected abstention behavior.

Admins/operators can promote or dismiss review items through controlled endpoints.

## Quality gates

The evaluation system evolved into multiple layers:

1. retrieval benchmark,
2. debug/exact retrieval benchmark,
3. evidence threshold calibration,
4. grounded answer evaluation,
5. citation/claim safety evaluation,
6. regression tracking.

A key project rule is that the final production threshold must be generated from measured corpus evidence instead of being selected because it “looks reasonable.”

See also:

- [`../authenticated-conversations.md`](../authenticated-conversations.md)
- [`../conversation-feedback.md`](../conversation-feedback.md)
- [`../quality-loop.md`](../quality-loop.md)
- [`../quality-gate.md`](../quality-gate.md)
