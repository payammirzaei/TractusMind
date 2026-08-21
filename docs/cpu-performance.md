# CPU-only retrieval performance

TractusMind is designed so the interactive query path does not require a GPU. Full corpus
synchronization is intentionally separated from user-facing retrieval: document embeddings are
computed during ingestion and stored in Qdrant, while a normal question only computes one dense
query embedding, one sparse query embedding, retrieves a small candidate set, and reranks that
candidate set.

## Production baseline

The current production topology allocates the API service a default `2.0` CPU and `4g` memory. The
API runs one Uvicorn process by default so the in-process ONNX models are not duplicated across
multiple workers. Ingestion runs in a separate Dramatiq worker with one process and one thread,
preventing a full source synchronization from competing with the interactive API inside the same
process.

The production Compose topology mounts `model_cache` at `/home/app/.cache` for both the API and
worker. On a platform such as Railway, use an equivalent persistent volume for that path when
possible. Without a persistent cache, a fresh deployment may need to download model artifacts
again before the first inference.

## Measurement workflow

`.github/workflows/cpu-performance.yml` runs the production FastEmbed model stack on a Linux GitHub
runner and constrains the benchmark process to at most two CPUs using `taskset`. The workload uses
the existing full-corpus benchmark questions and the production candidate count (`20`) and rerank
limit (`6`). Representative candidate payloads are deterministic and approximately 1,200 characters
each so the cross-encoder receives a realistic small-document workload without requiring a full
Qdrant corpus rebuild.

The report records:

- cold dense query initialization,
- cold sparse query initialization,
- cold cross-encoder initialization,
- steady-state dense query p50/p95,
- steady-state sparse query p50/p95,
- steady-state rerank p50/p95 for 20 candidates to 6 results,
- combined model-compute p50/p95,
- process maximum RSS,
- CPU affinity and runtime metadata.

The JSON report is uploaded as a 90-day GitHub Actions artifact.

## Why the first PR is measurement-only

The first run intentionally does not contain a made-up latency threshold. Runner measurements are
collected first, then a release budget can be pinned with explicit headroom from observed p95 and
memory use. That keeps the gate evidence-based and avoids tuning the system to an arbitrary number.

Once a production deployment exists, a second live latency smoke should add Qdrant network/search
and API overhead. External LLM latency is reported separately because it is provider-dependent and
is not a measure of the local CPU retrieval stack.

## Manual run

```bash
tractusmind-perf \
  --dataset benchmarks/full_corpus_v1.jsonl \
  --iterations 2 \
  --candidate-count 20 \
  --candidate-chars 1200 \
  --rerank-limit 6 \
  --output artifacts/cpu-performance.json
```

For a two-CPU Linux approximation matching the current API baseline:

```bash
taskset -c 0,1 tractusmind-perf --output artifacts/cpu-performance.json
```

Do not compare full-corpus ingestion duration with this benchmark. Ingestion can take many minutes
on CPU because thousands of document embeddings are generated once per changed source snapshot;
that work is not performed for every user question.
