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
- Tree-sitter/code-aware ingestion (next milestone)
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

**V0 — Foundation**

- [x] FastAPI service shell
- [x] Qdrant/PostgreSQL/Redis connectivity contract
- [x] API liveness/readiness checks
- [x] Background worker shell
- [x] Docker Compose local environment
- [x] CI lint + test
- [x] Evaluation directory
- [ ] Tractus-X source registry
- [ ] GitHub/docs ingestion
- [ ] code-aware chunking
- [ ] first dense retrieval benchmark

## License

Apache-2.0
