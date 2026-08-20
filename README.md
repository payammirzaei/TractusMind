# TractusMind

**A source-grounded AI engineering copilot for the Tractus-X ecosystem.**

TractusMind is being built to answer architecture, documentation, coding, debugging, semantic-model, and version-specific questions using traceable Tractus-X sources.

The project intentionally starts with retrieval quality and evaluation before UI work.

## Foundation stack

- Python 3.12
- FastAPI
- Qdrant for dense + sparse retrieval
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

## Source discovery, fetching, and chunking

Official Tractus-X sources are allowlisted in `config/sources.toml`. Discovery resolves every repository ref to an immutable commit SHA before any content is fetched.

```bash
# Inspect the pinned manifest for a source
tractusmind-ingest discover tractusx-sdk

# Fetch three selected files from that exact commit and inspect their metadata
tractusmind-ingest fetch tractusx-sdk --limit 3

# Fetch and smart-chunk three files, printing only traceability metadata
tractusmind-ingest chunk tractusx-sdk --limit 3

# Discover all enabled sources with the original inspection script
python scripts/discover_sources.py
```

Fetched files become canonical `RawDocument` objects containing a stable document ID, repository, commit SHA, blob SHA, language/content type, SHA-256 content hash, normalized UTF-8 text, and a source URL pinned to the exact commit.

Smart chunking keeps retrieval units source-traceable:

- Markdown is split by heading hierarchy before size limits are applied.
- Python, Java, Kotlin, TypeScript, and JavaScript are parsed with Tree-sitter and chunked by class/function/method symbols.
- Code chunks preserve parent symbols such as `ConnectorService -> create_asset`.
- YAML is chunked by top-level configuration keys.
- Turtle/SAMM content is chunked by semantic statements while retaining prefix context.
- Every chunk carries exact source line ranges and a commit-pinned citation URL.

`GITHUB_TOKEN` is optional for public repositories, but recommended to avoid low unauthenticated API rate limits.

If GitHub reports a truncated recursive tree, TractusMind refuses the ingestion instead of silently indexing an incomplete repository. Large repositories will get a selective subtree walker in a later ingestion milestone.

## Design principle

No hidden RAG magic. The system should make it possible to inspect:

```text
question
  -> query intent
  -> retrieved chunks
  -> hybrid scores
  -> reranked chunks
  -> final context
  -> generated answer
  -> sources + versions
  -> evaluation result
```

See [`docs/architecture.md`](docs/architecture.md) for the current architecture contract.

## Current milestone

**V0 — Foundation / Source Ingestion / Smart Chunking**

- [x] FastAPI service shell
- [x] Qdrant/PostgreSQL/Redis connectivity contract
- [x] Background worker shell
- [x] Docker Compose local environment
- [x] CI lint + test
- [x] Evaluation directory
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
- [ ] embedding generation + Qdrant indexing
- [ ] first dense retrieval benchmark

## License

Apache-2.0
