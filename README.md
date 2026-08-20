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

Search modes:

```bash
# Production default: hybrid candidates + cross-encoder reranking
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --limit 5

# Explicit comparison modes
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode dense --limit 5
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode hybrid --limit 5
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?" --mode rerank --limit 5
```

Fetched files become canonical `RawDocument` objects with stable IDs, commit SHA, blob SHA,
language/content type, SHA-256 content hash, normalized UTF-8 text, and commit-pinned URLs.

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
repository URLs, commit SHAs, paths, or line numbers. Structured `citation_ids` must exactly
match inline citations in the generated answer.

The claim verifier performs a second pass over the answer and evidence. It breaks the answer
into atomic factual claims and checks whether the citations attached to each claim directly
support it. Unknown citations, citations not present in the answer, unsupported claims, invalid
verifier output, and excessive claim counts all fail closed.

If verification fails, TractusMind returns an abstention rather than a supposedly grounded
answer. The verification report is preserved in the API response for inspection.

Source evidence is treated as untrusted data in both generation and verification prompts to
reduce prompt-injection risk. Missing LLM configuration does not prevent the API from starting;
`/v1/ask` returns `503` until a provider is configured.

## Retrieval benchmark

The fixed retrieval seed is stored in `benchmarks/dense_v0.jsonl`.

```bash
tractusmind-benchmark --mode all --k 5
tractusmind-benchmark --mode dense --k 5
tractusmind-benchmark --mode hybrid --k 5
tractusmind-benchmark --mode rerank --k 5
```

Current retrieval metrics:

- Recall@K / evidence hit rate
- MRR
- NDCG@K
- per-question first relevant rank and source trace

A benchmark hit is intentionally strict: the returned chunk must come from an expected source
and contain all expected terms for that case. Relevance thresholds remain unset until calibrated
from measured Tractus-X results rather than guessed from raw scores.

## Design principle

No hidden RAG magic. A production request should remain inspectable end to end:

```text
question
  -> query intent
  -> dense candidates
  -> sparse candidates
  -> RRF fusion
  -> hybrid score
  -> rerank score
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

**V4 — Claim-Verified Grounded Answers**

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
- [x] Prompt-injection-aware evidence framing
- [x] Structured/inline citation consistency gate
- [x] Atomic claim extraction and evidence verification
- [x] Fail-closed answer gate with verification report
- [ ] calibrated relevance / abstention thresholds
- [ ] answer-level groundedness and citation evaluation dataset
- [ ] version-aware query routing
- [ ] debugging-specific retrieval lane

## License

Apache-2.0
