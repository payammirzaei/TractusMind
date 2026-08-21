# 05 — Mission Control Frontend Evolution

## From backend utility to product

Once the backend pipeline was largely complete, the project shifted toward a browser experience that could expose the system as a serious engineering product rather than a collection of APIs.

The frontend became **TractusMind Mission Control**.

Current stack:

- Next.js 16
- React 19
- Tailwind CSS 4
- local shadcn-compatible UI primitives
- Motion
- lucide-react

## Design direction

The UI deliberately avoids generic “AI SaaS dashboard” styling. The design language moved toward a restrained industrial Mission Control aesthetic:

- graphite chassis surfaces,
- recessed evidence/inspection wells,
- tactile controls,
- cyan/amber instrumentation,
- explicit status indicators,
- flatter, highly readable chat surfaces.

The rule throughout the frontend work was: **visual sophistication is allowed; fake operational information is not**.

## Route model and RBAC

Main routes:

- `/` — Copilot
- `/overview` — Command Center
- `/sources` — Source fleet
- `/ops` — Operational runs
- `/quality` — Quality/review console
- `/admin` — Identity administration

Mission Control renders navigation and surfaces according to the current role.

## Copilot workbench

The chat workbench was expanded from a minimal prompt/answer surface into an inspectable engineering console.

Implemented capabilities include:

- quick engineering prompts,
- conversation history,
- smooth turn navigation,
- retry on failed questions,
- answer copy,
- feedback actions,
- route/model/evidence/verification badges,
- citation buttons,
- selected-citation provenance inspector,
- claim verification inspector,
- route → retrieve → rerank → verify processing rail.

Citation inspection exposes real backend fields such as repository, ref, snapshot, path, lines and retrieval/rerank signals when available.

Historical messages are intentionally conservative: the UI does not fabricate provenance that the backend did not preserve for an older turn.

## Source console

The Sources surface was turned into an operational console with:

- source search/filter,
- indexed/failed/locked counts,
- source detail inspector,
- configured ref,
- resolved version/snapshot,
- file counts,
- latest ingestion run,
- current errors,
- admin synchronization actions.

## Operations console

The Ops surface reads real backend endpoints and provides:

- runtime summary,
- ingestion runs,
- search/filter,
- run detail inspection,
- file/chunk counters,
- error inspection,
- periodic refresh.

## Quality console

The Quality surface exposes the feedback/review loop instead of treating feedback as a dead-end thumbs-up/down signal.

It includes:

- review search/filter,
- selected review inspector,
- promote/dismiss actions,
- root-cause classification,
- expected source IDs/terms,
- expected abstention configuration,
- validation before administrative promotion.

## Admin console

The Admin surface supports local identity operations:

- identity search/filter,
- role display/change,
- external IdP-managed identity distinction,
- API-key rotation,
- enable/disable,
- one-time credential provisioning/copy.

## Command Center (`/overview`)

A dedicated system-level overview was added after the individual consoles were mature.

It combines live information from:

- `/health/ready`,
- operations summary,
- source state,
- recent runs,
- quality summary,
- quality review queue.

The Command Center presents:

- nominal/degraded mission state,
- backend dependency readiness,
- source coverage/attention,
- ingestion activity,
- quality inbox/regression signals,
- knowledge/runtime/trust plane topology,
- current authenticated authority.

The page handles degraded health as a real state rather than crashing or replacing it with fake “online” indicators.

## Global command launcher

A Ctrl/⌘K launcher was added for role-aware navigation across Mission Control.

A later keyboard-conflict fix moved shortcut ownership into capture phase and stops propagation so individual surfaces cannot accidentally steal the same global shortcut.

## Resilience surfaces

We added product-level failure handling:

- route loading skeleton,
- themed 404,
- recoverable route error boundary,
- root-level global fail-safe.

This ensures a single rendering/runtime problem does not collapse into an unstyled Next.js error page.

## Live backend health

Mission Control polls real backend readiness and represents PostgreSQL, Redis and Qdrant state. Core/system status is derived from those checks rather than a hard-coded “production/online” label.

## Browser security boundary

Next.js production configuration was hardened with:

- standalone output,
- disabled `X-Powered-By`,
- nosniff,
- frame denial,
- referrer policy,
- permissions policy,
- COOP/CORP,
- production CSP,
- HSTS at Caddy.

The static CSP still allows the inline behavior required by the current Next.js runtime; nonce-based CSP is a possible future hardening step rather than a falsely documented current capability.

## Frontend CI maturity

Frontend validation evolved from build-only checks into a production-runtime test suite covering:

- dependency audit,
- typecheck,
- production build,
- real `next start` route smoke,
- BFF/session behavior,
- OIDC PKCE behavior,
- disabled-OIDC fail-closed behavior,
- production Docker image startup,
- Docker BFF smoke,
- development/production Compose topology validation,
- browser security header assertions.

See also [`../mission-control.md`](../mission-control.md).
