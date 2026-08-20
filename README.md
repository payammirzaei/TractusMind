# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind is being built to answer architecture, documentation, coding, debugging, semantic-model, and version-specific questions using traceable Tractus-X sources.

The project intentionally starts with retrieval quality and evaluation before UI work.

## Foundation stack

- Python 3.12
- FastAPI
- Qdrant for dense + sparse retrieval
- FastEmbed + `BAAI/bge-small-en-v1.5` for dense embeddings
- FastEmbed + `Qdrant/bm25` for sparse lexical retrieval
- RRF fusion inside Qdrant for hybrid retrieval
- PostgreSQL for application and ingestion state
- Redis + Dramatiq for background ingestion jobs
- Tree-sitter for AST-aware source-code chunking
- Cross-encoder reranking (next retrieval milestone)
- Docker / Docker Compose
- GitHub Actions
- Railway-ready environment configuration

## Local development

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`
- Qdrant dashboard: `http://localhost:6333/dashboard`

## Development without Docker

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
```

## Source discovery, chunking, indexing, and retrieval

Official Tractus-X sources are allowlisted in `config/sources.toml`. Discovery resolves every repository ref to an immutable commit SHA before any content is fetched.

```bash
# Inspect the pinned manifest for a source
tractusmind-ingest discover tractusx-sdk

# Fetch three selected files from that exact commit
tractusmind-ingest fetch tractusx-sdk --limit 3

# Fetch and smart-chunk three files
tractusmind-ingest chunk tractusx-sdk --limit 3

# Smoke-index a subset without cleaning previous source versions
tractusmind-ingest index tractusx-sdk --limit 10

# Full source hybrid index; stale commits are cleaned after successful upsert
tractusmind-ingest index tractusx-sdk

# Default: hybrid Dense + BM25 + RRF
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --limit 5

# Dense-only baseline against the same hybrid collection
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode dense --limit 5
```

Fetched files become canonical `RawDocument` objects containing a stable document ID, repository, commit SHA, blob SHA, language/content type, SHA-256 content hash, normalized UTF-8 text, and a source URL pinned to the exact commit.

Smart chunking keeps retrieval units source-traceable:

- Markdown is split by heading hierarchy before size limits are applied.
- Python, Java, Kotlin, TypeScript, and JavaScript are parsed with Tree-sitter and chunked by class/function/method symbols.
- Code chunks preserve parent symbols such as `ConnectorService -> create_asset`.
- YAML is chunked by top-level configuration keys.
- Turtle/SAMM content is chunked by semantic statements while retaining prefix context.
- Every chunk carries exact source line ranges and a commit-pinned citation URL.
- Chunk budgets are conservative for the dense model input window to reduce silent truncation.

Hybrid indexing enriches retrieval text with repository, component, path, language, section, and code-symbol context while preserving the original source text unchanged in Qdrant payloads. Every point stores both a named dense vector and a BM25 sparse vector. The sparse vector is configured with Qdrant's IDF modifier.

## Retrieval benchmark

The fixed retrieval seed is stored in `benchmarks/dense_v0.jsonl`. The runner evaluates Dense and Hybrid against the exact same indexed collection.

```bash
# Compare both modes at K=5
tractusmind-benchmark --mode both --k 5

# Run only one mode
tractusmind-benchmark --mode dense --k 5
tractusmind-benchmark --mode hybrid --k 5
```

Current metrics:

- Recall@K / evidence hit rate
- MRR
- NDCG@K
- per-question first relevant rank and source trace

A benchmark hit is intentionally strict: the returned chunk must come from an expected source and contain all expected terms for that case. Relevance thresholds remain unset until calibrated from measured Tractus-X retrieval results rather than guessed from cosine scores.

`GITHUB_TOKEN` is optional for public repositories, but recommended to avoid low unauthenticated API rate limits.

If GitHub reports a truncated recursive tree, TractusMind refuses the ingestion instead of silently indexing an incomplete repository. Large repositories will get a selective subtree walker in a later ingestion milestone.

## Design principle

No hidden RAG magic. The system should make it possible to inspect:

```text
question
  -> query intent
  -> dense candidates
  -> sparse candidates
  -> RRF fusion
  -> reranked chunks
  -> final context
  -> generated answer
  -> sources + versions
  -> evaluation result
```

See [`docs/architecture.md`](docs/architecture.md) for the current architecture contract.

## Current milestone

**V1 — Hybrid Retrieval Baseline**

- [x] FastAPI service shell
- [x] Qdrant/PostgreSQL/Redis connectivity contract
- [x] Background worker shell
- [x] Docker Compose local environment
- [x] CI lint + test
- [x] Tractus-X source registry
- [x] Version-pinned GitHub manifest discovery
- [x] Selective file filtering and archived-source protection
- [x] Commit-pinned content fetching
- [x] Canonical RawDocument metadata + content hashing
- [x] Incomplete-tree safety guard
- [x] Markdown heading-aware chunking
- [x] Tree-sitter code symbol chunking
- [x] YAML/Turtle structure-aware chunking
- [x] Stable KnowledgeChunk IDs + exact source line ranges
- [x] FastEmbed dense embeddings
- [x] BM25 sparse embeddings with IDF
- [x] Model-scoped hybrid Qdrant collection
- [x] Dense + sparse RRF fusion
- [x] Safe stale-commit cleanup after full source reindex
- [x] Dense/hybrid search CLI with scores and exact citations
- [x] Fixed retrieval benchmark seed
- [x] Recall@K / MRR / NDCG benchmark runner
- [ ] cross-encoder reranking
- [ ] calibrated relevance / abstention thresholds
- [ ] answer generation with grounded citations

## License

Apache-2.0
