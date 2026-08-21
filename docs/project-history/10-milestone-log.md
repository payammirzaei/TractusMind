# 10 — Chronological Milestone Log

This is a development-history summary, not a replacement for `git log`. It groups the important architectural milestones so future readers do not need to reconstruct the project from hundreds of individual edits.

## Phase A — Source-grounded backend foundation

The project began by establishing the backend primitives required for a trustworthy engineering copilot:

- FastAPI application structure,
- PostgreSQL state,
- Qdrant vector storage,
- GitHub source discovery/fetching,
- curated source registry,
- document normalization,
- smart chunking,
- dense embedding/indexing,
- retrieval endpoints/CLI.

The key early decision was that source repository/ref/snapshot provenance must survive from ingestion through answer citation.

## Phase B — Hybrid retrieval and evidence control

The retrieval architecture was expanded with:

- BM25-style sparse vectors,
- hybrid dense+sparse search,
- exact/debug retrieval lane,
- RRF/candidate fusion,
- cross-encoder reranking,
- structured query routing,
- source/ref/snapshot filters,
- evidence thresholding and abstention.

At this point the system became a controlled RAG pipeline rather than a plain semantic search wrapper.

## Phase C — Grounded answer and verification

The generation path added:

- bounded grounded context,
- citation construction/validation,
- claim verification,
- answer/abstain behavior,
- structured answer metadata for inspection.

The invariant “history is context, never evidence” became a core rule.

## Phase D — Stateful conversations and user quality loop

The backend then gained:

- owned conversations/messages,
- API-key identities,
- role hierarchy,
- feedback persistence,
- quality review objects,
- operator/admin review actions,
- evaluation and quality-gate tooling.

## Phase E — Background operations and production backend

Operational capabilities were added:

- Redis,
- Dramatiq workers,
- scheduler,
- incremental source synchronization,
- ingestion run state,
- provider retries/backoff/circuit breaking,
- Prometheus/OpenTelemetry metrics,
- Grafana/Alertmanager configuration,
- production Compose topology,
- migrations as startup gates,
- Docker secret support,
- backup/restore procedures.

## Phase F — Authentication hardening and enterprise identity

Authentication evolved from local API keys into a two-path model:

- local API identities,
- external OIDC identities.

The browser layer later added Authorization Code + PKCE and a server-side session/BFF boundary so bearer credentials are not persisted in browser storage.

## Phase G — Mission Control frontend

The frontend was built out in large feature passes rather than isolated cosmetic edits.

Major milestones included:

- live backend readiness in the shell,
- premium Copilot workbench,
- citation/provenance inspector,
- claim verification inspector,
- processing rail,
- Sources console,
- Ops console,
- Quality console,
- Admin console,
- global Ctrl/⌘K command launcher,
- `/overview` Command Center,
- responsive console visual system,
- loading/404/error/global fail-safe surfaces,
- live session revalidation,
- SSO-first login when configured.

Representative frontend development commits included work such as:

- `feat(ui): surface live backend readiness`
- `feat(ui): elevate copilot workbench interactions`
- `feat(ui): turn control decks into interactive consoles`
- `feat(ui): add global mission command launcher`
- `feat(ui): add live mission command center`
- `feat(ui): continuously revalidate live Mission Control sessions`

## Phase H — Frontend security and runtime CI

The frontend workflow was expanded to test the production artifact, not only source code.

Added/verified:

- npm audit,
- typecheck,
- Next.js production build,
- `next start` route smoke,
- BFF/session smoke,
- mock OIDC provider,
- PKCE verifier/challenge validation,
- disabled-SSO fail-closed smoke,
- Docker runtime smoke,
- browser security-header assertions,
- development/production Compose validation.

The production Next.js runtime was hardened and unnecessary package-manager tooling was removed from the final image after Trivy findings.

## Phase I — Green CI milestone

A temporary frontend/security diagnostic PR was used to obtain actionable GitHub Actions logs.

**PR #1 — `ci: validate frontend and security green gate`**

- status: merged,
- purpose: expose and fix frontend/security workflow failures,
- result: CI/test, Frontend/build and Security/Trivy reached green status on the verified candidate.

This completed the first formal release stage.

## Phase J — Full-stack integration milestone

A real Compose integration workflow was introduced and iterated through temporary diagnostic PRs.

It exposed and helped fix:

- loopback/container networking assumptions,
- missing `.env` fixture behavior,
- browser/internal origin mismatch behind reverse proxy.

The final gate successfully exercised the real Mission Control → BFF → FastAPI → PostgreSQL/Redis/Qdrant path with auth/RBAC and background services.

Temporary evidence PRs included #2, #3, #5 and #7. These were diagnostic and intentionally not merged as product changes.

## Phase K — Self-contained quality infrastructure

Quality validation was redesigned so GitHub Actions can create its own clean state:

- PostgreSQL service,
- Qdrant service,
- GitHub job token for public sources,
- fresh schema/corpus per run.

**PR #8 — `ci: verify self-contained quality infrastructure`**

- status: closed, not merged,
- purpose: prove the infrastructure assumptions,
- result: quality infrastructure itself was validated.

A permanent corpus-calibration workflow was then added to `main`.

## Phase L — Full-corpus calibration and native crash discovery

**PR #9 — `ci: run full-corpus calibration candidate`**

- status at snapshot time: open,
- purpose: execute all six sources and generate retrieval/threshold evidence.

The first run successfully reached real source ingestion but crashed during `tractusx-sdk` with native exit 139.

## Phase M — Tractus-X SDK SIGSEGV root cause and fix

**PR #10 — `ci: isolate embedding native crash`**

- status: closed, not merged,
- purpose: isolate dense vs sparse native embedding paths,
- result: both simple dense and sparse paths passed; embedding initialization alone was not the culprit.

The real SDK corpus was then traced through fetch/chunk/embed stages and the failure was narrowed to Python tree-sitter parsing.

**PR #11 — `fix: use crash-safe Python AST chunking`**

- status: merged,
- purpose: eliminate the native Python parser crash,
- change: Python symbol chunking moved to stdlib AST; other supported languages retain appropriate tree-sitter paths,
- validation: regression plus exact upstream `tractusx-sdk` corpus and normal CI/security/full-stack checks.

This is the durable product fix for the corpus-ingestion SIGSEGV.

## Phase N — Hardened production runtime gate

**PR #12 — `ci: prove hardened production runtime end to end`**

- status at snapshot time: open,
- purpose: boot and smoke the actual hardened production Compose topology,
- target behavior: Docker secrets, authenticated Redis, private backend services, read-only app containers, Mission Control, Caddy HTTPS, Secure `__Host-` session cookies, CSRF rejection and production BFF/admin/operator behavior.

This is current release-hardening work, not a historical diagnostic-only branch.

## PR snapshot (2026-08-21)

| PR | Purpose | Snapshot status | Product merge? |
| --- | --- | --- | --- |
| #1 | Frontend/security green gate | merged | yes |
| #2 | Full-stack diagnostic | closed | no |
| #3 | Full-stack release-candidate diagnostic | closed | no |
| #4 | Quality environment probe | closed | no |
| #5 | Full-stack final diagnostic | closed | no |
| #6 | Release-candidate diagnostic | open/stale | no; clean up |
| #7 | Proxy-origin diagnostic | closed | no |
| #8 | Quality infrastructure diagnostic | closed | no |
| #9 | Corpus calibration measurement | open | evidence branch |
| #10 | Native embedding diagnostic | closed | no |
| #11 | Crash-safe Python AST chunking | merged | yes |
| #12 | Hardened production runtime gate | open | candidate after green verification |

## Next historical milestone to record

The next entry should be created only when one of these is genuinely true:

1. the six-source calibration finishes and the measured threshold is pinned;
2. the hardened production runtime gate is merged green;
3. real LLM answer certification passes;
4. a live HTTPS deployment passes production smoke;
5. `v1.0.0` is tagged.
