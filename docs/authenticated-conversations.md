# Authentication, RBAC, and user-owned conversations

TractusMind supports two bearer identity modes that resolve into the same persisted `app_user`
identity and conversation-ownership model:

```text
opaque API key (tm_...)
        or
OIDC access token
        ↓
UserIdentity
        ↓
user / operator / admin
        ↓
owned conversations + RBAC
```

Anonymous `/v1/ask` remains supported, but anonymous history is never loaded into generation.

## API-key identities

Admins can create self-contained users through:

```http
POST /v1/ops/users
Authorization: Bearer <admin credential>
Content-Type: application/json

{"display_name":"Alice","role":"user"}
```

`X-TractusMind-Admin-Key` remains supported as a break-glass admin credential.

The plaintext `tm_...` key is returned only when created or rotated. PostgreSQL stores only its
SHA-256 digest and short prefix.

Roles for API-key identities are locally managed:

```text
user
operator
admin
```

## Enterprise OIDC/JWKS

Enable OIDC with an exact issuer URL and, preferably, the API audience:

```bash
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://id.example.com/realms/tractusmind
OIDC_AUDIENCE=tractusmind-api
OIDC_ALLOWED_ALGORITHMS=RS256
```

TractusMind loads standard OpenID Provider Configuration from:

```text
{issuer}/.well-known/openid-configuration
```

and verifies access-token signatures against the advertised `jwks_uri`.

Verification is fail-closed:

- configured issuer must match the discovery document exactly,
- JWT `iss`, `sub`, and `exp` are required,
- audience is verified when `OIDC_AUDIENCE` is configured,
- only algorithms in `OIDC_ALLOWED_ALGORITHMS` are accepted,
- a JWT `kid` must resolve to a JWKS key,
- an unknown `kid` triggers one forced JWKS refresh for key rotation,
- production provider URLs must use HTTPS,
- provider outages return `503`; invalid tokens return `401`.

Discovery and JWKS are cached with `OIDC_CACHE_TTL_SECONDS`. The token itself is still validated on
every request; only provider metadata/key retrieval is cached.

## External identity persistence

A verified token is resolved by the immutable pair:

```text
(issuer, subject)
```

The first successful login creates an `app_user` row with `auth_type=oidc`. Later logins reuse the
same user ID, so conversation ownership remains stable across token refreshes.

A locally disabled OIDC identity stays disabled. A later valid token does not automatically
re-enable it.

## Role mapping

Role claims are configurable dotted paths:

```bash
OIDC_ROLE_CLAIMS=roles,realm_access.roles,groups
OIDC_ADMIN_ROLES=tractusmind-admin
OIDC_OPERATOR_ROLES=tractusmind-operator
```

This covers common top-level role claims, Keycloak realm roles, and group-based mappings without
provider-specific code branches.

Resolution is least-privilege:

```text
matching admin role     -> admin
matching operator role  -> operator
anything else           -> user
```

OIDC roles are identity-provider managed. TractusMind admins may locally disable/enable an OIDC
identity, but cannot override its role through `/v1/ops/users`; role changes belong in the IdP.

API-key roles remain locally manageable.

## RBAC matrix

| Capability | user | operator | admin |
| --- | --- | --- | --- |
| Ask questions / owned conversations | yes | yes | yes |
| Submit feedback | yes | yes | yes |
| Read source/run/interaction/quality ops | no | yes | yes |
| Trigger source synchronization | no | no | yes |
| Dismiss/promote quality reviews | no | no | yes |
| Create/rotate/disable API-key users | no | no | yes |
| Assign API-key roles | no | no | yes |

`admin` inherits `operator` access. Operator endpoints return `403` for authenticated users with an
insufficient role and `401` when no valid operations identity is present.

## Break-glass admin

`OPS_ADMIN_KEY` / `X-TractusMind-Admin-Key` remains available for emergency or bootstrap access. It
is treated as admin and should not be the normal enterprise access path once OIDC is configured.

Keep this key in the deployment secret store, rotate it independently, and avoid distributing it to
human operators.

## Conversation ownership

Authenticated conversations store `conversation.owner_user_id`. Access is fail-closed: a user may
continue or read a conversation only when the persisted owner matches the authenticated identity.
Cross-user access returns `404`, not `403`, so conversation existence is not leaked.

Existing anonymous conversations stay anonymous and are not auto-claimed merely because an
authenticated user knows their UUID.

## Bounded history and grounding

Only completed interactions can become conversation context, bounded by:

```bash
HISTORY_MAX_TURNS=6
HISTORY_MAX_CHARS=6000
```

History remains context, not evidence. Previous assistant answers cannot become citations and do
not bypass current retrieval, backend citation validation, or atomic claim verification.

## Database migration

V21 adds:

```text
0001_core_schema
  -> 0002_user_auth
  -> 0003_oidc_rbac
```

`0003_oidc_rbac` adds identity type, role, OIDC issuer/subject, and allows API-key fields to be null
for external identities. `(oidc_issuer, oidc_subject)` is unique.

Downgrading across `0003_oidc_rbac` is deliberately blocked if OIDC identities already exist,
because converting those rows back into mandatory API-key users would require destructive data
loss.
