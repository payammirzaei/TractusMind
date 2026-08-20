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
- FastEmbed cross-encoder reranking with `Xenova/ms-marco-MiniLM-L-6-v2`
- OpenAI-compatible LLM provider interface for grounded generation
- PostgreSQL for application and ingestion state
- Redis + Dramatiq for background ingestion jobs
- Tree-sitter for AST-aware source-code chunking
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
tractusmind-ingest discover tractusx-sdk
tractusmind-ingest fetch tractusx-sdk --limit 3
tractusmind-ingest chunk tractusx-sdk --limit 3
tractusmind-ingest index tractusx-sdk --limit 10
tractusmind-ingest index tractusx-sdk
```

Search modes:

```bash
# Production-oriented default: hybrid candidates + cross-encoder reranking
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --limit 5

# Explicit comparison modes
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode dense --limit 5
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode hybrid --limit 5
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode rerank --limit 5
```

Fetched files become canonical `RawDocument` objects containing a stable document ID, repository, commit SHA, blob SHA, language/content type, SHA-256 content hash, normalized UTF-8 text, and a source URL pinned to the exact commit.

Smart chunking keeps retrieval units source-traceable:

- Markdown is split by heading hierarchy before size limits are applied.
- Python, Java, Kotlin, TypeScript, and JavaScript are parsed with Tree-sitter and chunked by class/function/method symbols.
- Code chunks preserve parent symbols such as `ConnectorService -> create_asset`.
- YAML is chunked by top-level configuration keys.
- Turtle/SAMM content is chunked by semantic statements while retaining prefix context.
- Every chunk carries exact source line ranges and a commit-pinned citation URL.
- Chunk budgets are conservative for the dense/reranker input windows to reduce silent truncation.

Hybrid indexing enriches retrieval text with repository, component, path, language, section, and code-symbol context while preserving the original source text unchanged in Qdrant payloads. Every point stores both a named dense vector and a BM25 sparse vector. The sparse vector is configured with Qdrant's IDF modifier.

The reranking stage takes a limited hybrid candidate set, scores each query/chunk pair with a cross-encoder, and returns only the strongest evidence. Both the original retrieval score and the reranker score are retained for later debugging and observability.

## Grounded answer generation

Configure any OpenAI-compatible chat-completions provider:

```bash
LLM_BASE_URL=https://provider.example/v1
LLM_API_KEY=...
LLM_MODEL=...
```

Then ask TractusMind through the API:

```http
POST /v1/ask
Content-Type: application/json

{
  "question": "How do I create an asset with the Tractus-X SDK?"
}
```

The production answer path is:

```text
question
  -> hybrid retrieval
  -> cross-encoder reranking
  -> bounded evidence context
  -> LLM
  -> backend-validated citations
  -> grounded answer or abstention
```

Evidence IDs such as `[S1]` are assigned by the backend. The LLM is not trusted to invent repository URLs, commit SHAs, paths, or line numbers. Returned citation metadata is mapped back to the exact retrieved chunk after generation.

Source evidence is explicitly treated as untrusted data in the generation prompt to reduce prompt-injection risk. If no usable evidence exists, if the configured relevance cutoff removes all evidence, or if the model invents citation IDs, TractusMind abstains instead of returning a grounded answer.

LLM configuration is lazy: missing `LLM_BASE_URL` or `LLM_MODEL` does not prevent the API from starting. `/v1/ask` returns `503` until a provider is configured.

## Retrieval benchmark

The fixed retrieval seed is stored in `benchmarks/dense_v0.jsonl`. The runner evaluates all retrieval stages against the exact same indexed collection.

```bash
# Dense vs Hybrid vs Hybrid + Reranker
tractusmind-benchmark --mode all --k 5

# Individual modes
tractusmind-benchmark --mode dense --k 5
tractusmind-benchmark --mode hybrid --k 5
tractusmind-benchmark --mode rerank --k 5
```

Current metrics:

- Recall@K / evidence hit rate
- MRR
- NDCG@K
- per-question first relevant rank and source trace

A benchmark hit is intentionally strict: the returned chunk must come from an expected source and contain all expected terms for that case. Relevance thresholds remain unset until calibrated from measured Tractus-X retrieval results rather than guessed from raw scores.

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
  -> hybrid candidate score
  -> cross-encoder rerank score
  -> final evidence
  -> generated answer
  -> validated citations
  -> sources + versions
  -> evaluation result
```

See [`docs/architecture.md`](docs/architecture.md) for the current architecture contract.

## Current milestone

**V3 — Grounded Answer Generation**

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
- [x] Dense/hybrid/reranked search CLI
- [x] Cross-encoder reranking with preserved first-stage scores
- [x] Fixed retrieval benchmark seed
- [x] Dense vs Hybrid vs Reranked benchmark runner
- [x] OpenAI-compatible grounded generation provider
- [x] Backend-owned citation IDs and exact source mapping
- [x] `/v1/ask` API endpoint
- [x] Prompt-injection-aware evidence framing
- [x] Fail-closed citation validation and abstention
- [ ] calibrated relevance / abstention thresholds
- [ ] claim-level groundedness verifier
- [ ] answer-level groundedness and citation evaluation

## License

Apache-2.0
