# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind answers architecture, documentation, coding, debugging, semantic-model, and
version-specific questions using traceable Tractus-X sources. Retrieval quality, source
provenance, and evaluation come before UI work.

## Foundation stack

- Python 3.12 + FastAPI
- Qdrant dense + sparse retrieval
- FastEmbed `BAAI/bge-small-en-v1.5` dense embeddings
- FastEmbed `Qdrant/bm25` sparse lexical retrieval
- Qdrant RRF hybrid fusion
- FastEmbed cross-encoder reranking with `Xenova/ms-marco-MiniLM-L-6-v2`
- Deterministic version-aware query routing
- OpenAI-compatible LLM provider interface
- Claim-level groundedness verification
- PostgreSQL for application and ingestion state
- Redis + Dramatiq for background ingestion jobs
- Tree-sitter for AST-aware code chunking
- Docker / Docker Compose
- GitHub Actions
- Railway-ready environment configuration

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Useful endpoints:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`
- Qdrant dashboard: `http://localhost:6333/dashboard`

Without Docker:

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

## Source ingestion and retrieval

Official Tractus-X sources are allowlisted in `config/sources.toml`. Every repository ref is
resolved to an immutable commit SHA before content is fetched.

```bash
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest fetch tractusx-sdk --limit 3
tractusmind-ingest chunk tractusx-sdk --limit 3
tractusmind-ingest index tractusx-sdk --limit 10
tractusmind-ingest index tractusx-sdk
```

Fetched files become canonical `RawDocument` objects with stable IDs, source/version ref,
commit SHA, blob SHA, language/content type, SHA-256 content hash, normalized UTF-8 text, and
commit-pinned URLs. `version_ref` is propagated into every `KnowledgeChunk`, Qdrant payload,
retrieval hit, evidence block, and answer citation.

After upgrading an older index to this milestone, run a full source re-index to backfill
`version_ref` on existing Qdrant payloads before using explicit `ref:` filters.

Smart chunking keeps retrieval units source-traceable:

- Markdown: heading hierarchy aware
- Python/Java/Kotlin/TypeScript/JavaScript: Tree-sitter symbol aware
- Code chunks: parent symbol relationships preserved
- YAML: top-level configuration aware
- Turtle/SAMM: semantic statement aware
- Every chunk: exact line range + commit-pinned citation URL

Hybrid indexing stores both a named dense vector and a BM25 sparse vector for every chunk.
The first stage uses dense + BM25 retrieval with RRF fusion. A cross-encoder then reranks a
small candidate set while preserving both first-stage and reranker scores.

## Version-aware query routing

Every production query is routed before retrieval. The router is deterministic and has no LLM
cost. It currently recognizes:

- SDK
- EDC
- Digital Twin Registry / DTR
- Semantic Models / SAMM
- Release/version questions
- Debug/error questions
- General fallback

The route records `intent`, selected `source_ids`, detected semantic `version`, explicit `ref`,
explicit `commit_sha`, and human-readable routing reasons. Source/ref/commit constraints become
Qdrant payload filters before dense/BM25 retrieval.

```bash
# SDK route -> tractusx-sdk + docs
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?"

# Debug route -> EDC-focused source filter
tractusmind-ingest search "EDC connector returns 500 error during transfer"

# Release version is detected and routed to release evidence
tractusmind-ingest search "What changed for SAMM in release 24.05?"

# Explicit indexed ref/commit constraints are hard filters
tractusmind-ingest search "Check EDC ref:v0.9.0 commit:abcdef1234567 connector behavior"
```

Semantic versions such as `24.05` are not blindly converted into a hard `version_ref` filter,
because one release repository/ref may document several releases. Explicit `ref:` and `commit:`
constraints are exact and fail closed when matching indexed provenance is unavailable.

Search output includes the complete route trace plus `version_ref`, commit SHA, source ID, path,
line range, retrieval score, and rerank score for every hit.

## Grounded answer generation

Configure any OpenAI-compatible chat-completions provider:

```bash
LLM_BASE_URL=https://provider.example/v1
LLM_API_KEY=...
LLM_MODEL=...
```

Then ask:

```http
POST /v1/ask
Content-Type: application/json

{
  "question": "How do I create an asset with the Tractus-X SDK?"
}
```

Production answer path:

```text
question
  -> deterministic query routing
  -> source/ref/commit payload filtering
  -> dense + BM25 retrieval
  -> RRF fusion
  -> cross-encoder reranking
  -> bounded evidence context
  -> grounded LLM generation
  -> backend citation validation
  -> claim-level evidence verification
  -> final answer or abstention
```

Evidence IDs such as `[S1]` are assigned by the backend. The model is not trusted to invent
repository URLs, source IDs, refs, commit SHAs, paths, or line numbers. Structured `citation_ids`
must exactly match inline citations in the generated answer.

The API response preserves the route decision and the exact `version_ref` + commit provenance for
each citation. The claim verifier performs a second pass over the answer and evidence, breaks the
answer into atomic factual claims, and checks whether each cited source directly supports it.

If verification fails, TractusMind returns an abstention rather than a supposedly grounded
answer. The verification report is preserved in the API response for inspection.

## Retrieval benchmark

The fixed retrieval seed is stored in `benchmarks/dense_v0.jsonl`.

```bash
tractusmind-benchmark --mode all --k 5
tractusmind-benchmark --mode dense --k 5
tractusmind-benchmark --mode hybrid --k 5
tractusmind-benchmark --mode rerank --k 5
```

All benchmark modes now use the same deterministic router as production. Per-case reports include
the route trace as well as retrieval metrics.

Current retrieval metrics:

- Recall@K / evidence hit rate
- MRR
- NDCG@K
- per-question first relevant rank and source trace

## Answer evaluation and abstention calibration

`benchmarks/answer_v0.jsonl` contains 10 answerable Tractus-X questions and 6 deliberately
unanswerable negative cases. The negative set prevents an always-answer system from looking
artificially good.

Calibrate the reranker evidence threshold without calling the LLM:

```bash
tractusmind-answer-eval calibrate --max-unsafe-rate 0
```

Calibration now uses the same query router and source filters as production. The sweep reports:

- recommended `MINIMUM_RELEVANCE_SCORE`
- true accept rate on answerable questions
- false abstention rate
- unsafe evidence accept rate on negative questions
- balanced accuracy

The recommended value is printed as an environment-variable assignment. It is not written into
the repository automatically because calibration depends on the indexed corpus and reranker.

With an LLM provider configured, run the full answer gate:

```bash
tractusmind-answer-eval evaluate
```

End-to-end metrics:

- grounded answer accuracy
- citation correctness against expected source IDs
- claim support rate from the verification report
- false abstention rate on answerable cases
- unsafe answer rate on unanswerable cases

Calibration and answer evaluation are intentionally separate. The former measures the evidence
acceptance boundary without LLM variability; the latter measures the complete production path.

## Design principle

No hidden RAG magic. A production request should remain inspectable end to end:

```text
question
  -> detected intent
  -> source/version/ref/commit route
  -> payload filter
  -> dense candidates
  -> sparse candidates
  -> RRF fusion
  -> hybrid score
  -> rerank score
  -> evidence threshold
  -> final evidence
  -> generated answer
  -> citation validation
  -> atomic claims
  -> claim/evidence verdicts
  -> final answer or abstention
  -> evaluation result
```

See [`docs/architecture.md`](docs/architecture.md) for the architecture contract.

## Current milestone

**V6 — Version-Aware Query Routing**

- [x] FastAPI service shell
- [x] Qdrant/PostgreSQL/Redis connectivity contract
- [x] Background worker shell
- [x] Docker Compose local environment
- [x] CI lint + test
- [x] Tractus-X source registry
- [x] Version-pinned GitHub manifest discovery
- [x] Commit-pinned content fetching
- [x] Canonical `RawDocument` provenance
- [x] Markdown / code / YAML / Turtle smart chunking
- [x] Stable `KnowledgeChunk` IDs + exact line ranges
- [x] Dense embeddings + BM25 sparse embeddings
- [x] Model-scoped hybrid Qdrant collection
- [x] Dense + sparse RRF fusion
- [x] Cross-encoder reranking with preserved first-stage scores
- [x] Dense vs Hybrid vs Reranked benchmark runner
- [x] OpenAI-compatible grounded generation provider
- [x] Backend-owned citation IDs and exact source mapping
- [x] `/v1/ask` API endpoint
- [x] Structured/inline citation consistency gate
- [x] Atomic claim extraction and evidence verification
- [x] Fail-closed answer gate with verification report
- [x] Positive + negative answerability benchmark seed
- [x] Safety-first reranker threshold calibration
- [x] Grounded/citation/claim/abstention evaluation metrics
- [x] Deterministic SDK/EDC/DTR/SAMM/release/debug routing
- [x] Semantic version extraction + explicit ref/commit constraints
- [x] Qdrant source/ref/commit payload filters
- [x] `version_ref` provenance from ingestion through citations
- [x] Route traces in CLI, API responses, benchmark, and calibration
- [ ] run calibration against a fully indexed corpus and persist the measured threshold
- [ ] debugging-specific exact-search retrieval lane
- [ ] incremental re-indexing and source-state persistence

## License

Apache-2.0
