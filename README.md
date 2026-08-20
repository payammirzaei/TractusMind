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
- Debug exact phrase/symbol/path retrieval with full-text payload indexing
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

After upgrading an older index to this milestone, run a full source re-index. This backfills both
`version_ref` and the new `debug_text` payload used by exact debug lookup. Index creation also adds
a Qdrant full-text index with whitespace tokenization and phrase matching.

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
Qdrant payload filters before retrieval.

```bash
# SDK route -> tractusx-sdk + docs
tractusmind-ingest search "How do I create an asset with the Tractus-X SDK?"

# Debug route -> EDC-focused source filter + exact debug lane
tractusmind-ingest search "EDC connector returns 500 error during transfer"

# Release version is detected and routed to release evidence
tractusmind-ingest search "What changed for SAMM in release 24.05?"

# Explicit indexed ref/commit constraints are hard filters
tractusmind-ingest search "Check EDC ref:v0.9.0 commit:abcdef1234567 connector behavior"
```

Semantic versions such as `24.05` are not blindly converted into a hard `version_ref` filter,
because one release repository/ref may document several releases. Explicit `ref:` and `commit:`
constraints are exact and fail closed when matching indexed provenance is unavailable.

## Debug retrieval lane

Queries routed as `debug` use an additional exact-search lane before cross-encoder reranking.
The query parser extracts engineering signals such as quoted error text, exception classes,
CamelCase/snake_case identifiers, dotted config keys, file paths, environment-style identifiers,
and HTTP 4xx/5xx codes.

The debug path is:

```text
debug query
  -> route/source/ref/commit filter
  -> exact phrase + symbol + parent-symbol + path lookup
  -> normal dense + BM25 hybrid retrieval
  -> weighted RRF across exact + hybrid candidates
  -> cross-encoder reranker
  -> final evidence
```

Exact lookup uses the `debug_text` Qdrant payload field, which combines path, symbols, section
metadata, and original chunk text. Exact symbol/path hits receive stronger first-stage weights,
but the cross-encoder still makes the final evidence ordering decision.

Every retrieval hit preserves `debug_score` and `retrieval_methods`, for example
`exact_symbol`, `exact_phrase`, `identifier_text`, and `hybrid`. The same provenance is exposed
through answer citations and the search CLI.

Debug fusion settings are configurable:

```bash
DEBUG_EXACT_K=30
DEBUG_RRF_K=60
DEBUG_EXACT_WEIGHT=1.5
DEBUG_HYBRID_WEIGHT=1.0
```

If an older index has not yet been re-indexed with `debug_text`, the exact lane can return no
candidates while the normal hybrid lane continues to function.

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
  -> normal hybrid OR debug exact+hybrid candidate generation
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

The API response preserves the route decision, retrieval-method trace, and exact
`version_ref` + commit provenance for each citation. The claim verifier performs a second pass
over the answer and evidence, breaks the answer into atomic factual claims, and checks whether
each cited source directly supports it.

If verification fails, TractusMind returns an abstention rather than a supposedly grounded
answer. The verification report is preserved in the API response for inspection.

## Retrieval benchmark

The general retrieval seed is stored in `benchmarks/dense_v0.jsonl`.

```bash
tractusmind-benchmark --mode all --k 5
tractusmind-benchmark --mode dense --k 5
tractusmind-benchmark --mode hybrid --k 5
tractusmind-benchmark --mode rerank --k 5
```

Debug-specific retrieval uses a separate seed built from identifiers verified in current
Tractus-X sources:

```bash
tractusmind-benchmark \
  --dataset benchmarks/debug_v0.jsonl \
  --mode rerank \
  --k 5
```

All benchmark modes use the same deterministic router as production. Per-case reports include
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

Calibration uses the same router and retrieval services as production. The sweep reports:

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
  -> exact debug candidates when applicable
  -> fusion score + retrieval methods
  -> cross-encoder rerank score
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

**V7 — Debug Retrieval Lane**

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
- [x] Exact debug phrase/symbol/path/config lookup
- [x] Debug + hybrid weighted RRF fusion
- [x] Retrieval-method/debug-score provenance
- [x] Real-source debug retrieval benchmark seed
- [ ] run full-corpus debug benchmark and tune fusion weights
- [ ] run calibration against a fully indexed corpus and persist the measured threshold
- [ ] incremental re-indexing and source-state persistence

## License

Apache-2.0
