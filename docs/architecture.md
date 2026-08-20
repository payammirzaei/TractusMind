# Architecture

TractusMind is designed as a source-grounded engineering copilot rather than a generic chatbot.
The first production-shaped deployment separates request serving, ingestion work, retrieval storage, application state, and job orchestration.

```text
Public Internet
      |
      v
 FastAPI API
      |
      +---------------- private network ----------------+
      |                 |             |                 |
      v                 v             v                 v
 Ingestion Worker     Qdrant       PostgreSQL          Redis
                         |
                  Dense + Sparse
                    Retrieval
```

## Responsibilities

- **FastAPI**: query API, health endpoints, orchestration, and later authentication.
- **Worker**: crawling, parsing, code-aware chunking, embeddings, and incremental indexing.
- **Qdrant**: dense/sparse retrieval vectors plus chunk retrieval metadata.
- **PostgreSQL**: source registry, versions/commits, ingestion runs, evaluations, conversations, and feedback.
- **Redis**: background job queue, locks, and short-lived cache.
- **S3-compatible storage**: immutable/raw source snapshots and ingestion artifacts. The configuration contract exists in V0; integration arrives with source ingestion.

## Retrieval direction

The retrieval pipeline will evolve deliberately:

1. Dense baseline
2. Dense + sparse hybrid retrieval
3. RRF fusion
4. Cross-encoder reranking
5. Version- and metadata-aware filtering
6. Code-aware and graph-enhanced retrieval only when benchmark results justify it

Every answer should remain traceable to repository/file/version/commit/chunk and retrieval evidence.
