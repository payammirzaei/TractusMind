# 02 — Backend and RAG Architecture Evolution

## Backend foundation

The backend evolved into a FastAPI service with explicit separation between application concerns, source ingestion, retrieval, generation, state, authentication, operations and evaluation.

Major runtime dependencies:

- FastAPI / Uvicorn
- PostgreSQL + SQLAlchemy + Alembic
- Redis
- Dramatiq workers
- Qdrant
- FastEmbed dense/sparse embeddings
- local cross-encoder reranking
- OpenAI-compatible LLM provider boundary
- Prometheus/OpenTelemetry instrumentation

## Retrieval-first design

The central architectural decision was to make retrieval and evidence quality determine whether generation is allowed to proceed.

The effective request flow became:

```text
question
  -> conversation ownership check
  -> bounded conversation history
  -> query router
  -> source/ref/snapshot filter
  -> dense retrieval
  -> BM25 sparse retrieval
  -> exact/debug retrieval lane
  -> candidate fusion / RRF
  -> reranking
  -> evidence threshold
  -> grounded prompt assembly
  -> generation
  -> citation validation
  -> claim verification
  -> answer or abstention
```

This is materially different from a simple vector-search chatbot because the answer path includes multiple opportunities to fail closed.

## Deterministic routing

A query router is used to infer structured retrieval intent before evidence search. Routing can narrow:

- component/source families,
- repositories,
- exact refs,
- immutable snapshot commits,
- debug/exact-match behavior.

The important design rule is that explicit user constraints are never silently broadened. If a requested ref or snapshot is unavailable, the system should fail closed rather than cite a neighboring version.

## Hybrid retrieval

The retrieval stack combines:

- dense semantic embeddings,
- sparse BM25-style embeddings,
- an exact/debug retrieval path,
- fusion,
- cross-encoder reranking.

Qdrant stores named dense and sparse vectors. Sparse vectors use Qdrant IDF behavior, while dense embeddings use the configured BGE model.

The collection name is model-scoped so changing embedding identities does not silently mix incompatible vectors in one collection.

## Reranking

Dense/sparse search is used to produce candidates. A local cross-encoder then produces the final ranking signal used by evidence thresholding.

This was important for two reasons:

1. semantic retrieval alone can surface plausible-but-wrong code/docs;
2. exact lexical hits matter heavily in engineering questions containing class names, APIs, errors, configuration keys and commit/ref terminology.

## Debug retrieval lane

A separate debug/exact retrieval path was added so engineering questions involving literal identifiers are not forced through only semantic similarity.

The debug lane and normal hybrid lane are fused rather than treated as mutually exclusive systems.

## Evidence threshold and abstention

The generation path is intentionally gated by a reranker/evidence threshold.

We explicitly avoided inventing the final production threshold. The current process is:

1. ingest the complete six-source corpus,
2. run evaluation datasets,
3. measure safe vs unsafe evidence scores,
4. calculate a zero-unsafe threshold candidate,
5. persist a reproducibility manifest,
6. pin the measured threshold into the production quality configuration.

This is one of the remaining v1 certification steps.

## Grounded generation

Generation receives bounded evidence rather than arbitrary source material. The prompt is constructed from selected evidence chunks and bounded conversational context.

Key safety/quality invariants:

- history cannot become evidence;
- historical assistant messages cannot become citations;
- citations must map back to retrieved chunks;
- citations expose repository/ref/snapshot/path/line provenance;
- unsupported claims are detected by the verification layer;
- insufficient evidence produces abstention.

## Claim verification

A claim-verification stage was introduced after generation. Mission Control exposes claim-level support state so a reviewer can distinguish:

- supported claims,
- unsupported claims,
- citation relationships.

This turned the answer object from a plain string into an inspectable engineering result.

## Provider resilience

The backend provider boundary includes bounded timeouts, retries/backoff and circuit-breaker behavior for external services such as GitHub and the LLM provider.

The project deliberately treats provider failure as an expected runtime condition instead of allowing an external outage to destabilize the whole application.

See also:

- [`../architecture.md`](../architecture.md)
- [`../provider-resilience.md`](../provider-resilience.md)
- [`../quality-gate.md`](../quality-gate.md)
