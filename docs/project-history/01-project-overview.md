# 01 — Project Overview and Goals

## What TractusMind became

TractusMind is a source-grounded AI engineering copilot for the Eclipse Tractus-X ecosystem. The product is designed to answer engineering questions from a curated, inspectable knowledge base while preserving exact provenance and exposing the operational state of ingestion, retrieval, quality, authentication, and system health through a browser-based Mission Control.

The end-state architecture is not a generic chatbot. It is an engineering system composed of three major planes:

1. **Knowledge plane** — curated Tractus-X repositories, immutable refs/snapshots, document parsing, chunking, dense+sparse indexing and source state.
2. **Runtime plane** — FastAPI, PostgreSQL, Redis, Qdrant, workers, scheduler, retrieval/reranking, grounded generation and claim verification.
3. **Trust/operations plane** — authentication/RBAC, conversations, feedback, quality review, observability, security boundaries, CI gates and production deployment controls.

Mission Control sits above those planes and makes them inspectable.

## Original problem we were solving

Engineering assistants become dangerous when they can produce plausible answers without showing where facts came from. TractusMind was built around the opposite behavior:

```text
question
  -> owned conversation context
  -> deterministic routing
  -> source/ref/snapshot constraints
  -> dense + sparse retrieval
  -> exact/debug retrieval lane
  -> RRF / candidate fusion
  -> reranking
  -> evidence threshold
  -> grounded generation
  -> citation validation
  -> claim verification
  -> answer or abstain
```

The goal is not only to answer a question. The goal is to make the answer **auditable**.

## Core product requirements that shaped the implementation

### Grounding

- Only indexed source material can support factual answers.
- Conversation history is context only.
- Assistant history cannot become citations.
- Explicit source/ref/commit filters fail closed.
- Low-evidence questions must abstain rather than fabricate confidence.

### Inspectability

Operators must be able to inspect:

- source configuration and immutable snapshots,
- ingestion runs and errors,
- retrieval and reranking behavior,
- answer citations and claim verification,
- user feedback and review queues,
- backend readiness and dependency health,
- authenticated identities and roles.

### Production orientation

The project was deliberately pushed beyond a local demo. The target includes:

- PostgreSQL state and migrations,
- Redis-backed worker scheduling,
- Qdrant hybrid retrieval,
- Dockerized runtime,
- Caddy TLS edge,
- OIDC/API-key authentication,
- security scanning,
- real full-stack integration CI,
- observability and alerting,
- backup/restore procedures,
- release images with SBOM/provenance.

## The six curated Tractus-X sources

The production knowledge registry currently targets six allowlisted source families:

- `tractusx-sdk`
- `tractusx-edc`
- `digital-twin-registry`
- `semantic-models`
- `tractusx-docs`
- `tractusx-release`

The registry intentionally avoids crawling an entire GitHub organization. Source quality, reproducibility and retrieval precision matter more than raw corpus size.

## Product surfaces

Mission Control currently exposes these principal routes:

- `/` — Copilot
- `/overview` — Command Center
- `/sources` — source fleet and provenance
- `/ops` — ingestion/runtime operations
- `/quality` — feedback and quality review
- `/admin` — identity and role administration

Role hierarchy:

```text
user < operator < admin
```

## Definition of done for v1

For this project, “100%” means more than feature completion. A v1 release is considered ready only when:

- backend and frontend CI are green,
- security scans are green,
- real full-stack integration is green,
- all six sources can be ingested reproducibly,
- retrieval calibration is measured from the real corpus,
- answer-quality certification runs against a real LLM endpoint,
- hardened production topology is exercised,
- a real HTTPS deployment passes smoke tests,
- documentation and release artifacts are complete,
- the repository is tagged `v1.0.0`.
