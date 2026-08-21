# Changelog

All notable changes to TractusMind are documented here.

## [Unreleased]

### Added
- Source-grounded Tractus-X engineering copilot with deterministic source/ref/commit routing.
- Dense + BM25 hybrid retrieval, debug retrieval lane, RRF fusion, cross-encoder reranking, citation validation, and atomic claim verification.
- Six-source allowlisted Tractus-X ingestion with incremental PostgreSQL/Qdrant synchronization.
- Persisted conversations, feedback, quality review, reviewed regression promotion, and measurable quality gates.
- API-key authentication plus enterprise OIDC/JWKS validation and role mapping.
- Mission Control frontend with Copilot, Command Center, Sources, Operations, Quality, and Admin consoles.
- HttpOnly BFF session boundary and Authorization Code + PKCE browser SSO.
- Real full-stack Docker integration gate covering PostgreSQL, Redis, Qdrant, FastAPI, workers, scheduler, and Mission Control.
- Hardened production Compose topology with Docker secrets, private service networking, read-only application containers, Caddy HTTPS edge, and production endpoint smoke tests.
- Backend and Mission Control multi-architecture GHCR release images with SBOM and provenance.
- Fail-closed release preflight that blocks tags until quality calibration is human-reviewed and pinned.
- Project-history documentation under `docs/project-history/`.

### Security
- Trivy filesystem and container image scans for HIGH/CRITICAL findings.
- Secure `__Host-` production session cookies and immediate rejected-session expiry.
- Cross-site mutation rejection for session and BFF write paths.
- Nonce-based browser CSP with `strict-dynamic`, enforced through the Next.js application boundary and preserved by Caddy.
- OIDC state validation, PKCE S256, safe return-path validation, bounded provider timeouts, and no browser-stored bearer token.
- Production runtime smoke verifies TLS, HSTS, browser headers, private services, read-only roots, session/RBAC, and logout.

### Fixed
- Frontend dependency findings that caused `npm audit` and Trivy failures.
- Docker CI networking between Mission Control and backend fixtures.
- Reverse-proxy origin canonicalization for secure same-origin mutations behind Docker/Caddy.
- Caddy internal-CA trust handling in production smoke tests.
- Python native parser SIGSEGV by moving Python structure extraction to the standard-library AST.
- Java native tree-sitter crash class by using deterministic line-bounded crash-safe code chunks; retrieval quality remains subject to corpus calibration.

### Release blockers
- Complete the six-source corpus calibration and review/pin `minimum_relevance_score` in `config/quality_gate.toml`.
- Run grounded-answer certification against the selected real OpenAI-compatible LLM.
- Deploy to the real HTTPS production target and pass production smoke.
- Tag `v1.0.0` only after `python scripts/release_preflight.py` passes.
