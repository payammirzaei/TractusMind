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

## Certified measurement

The first CPU Performance measurement was GitHub Actions run `32467484000`, artifact `9441253213`.
The benchmark process was constrained to two CPUs and used the production model stack, 12 existing
full-corpus benchmark questions, 20 rerank candidates per question, approximately 1,200 characters
per candidate, two iterations, and a final rerank limit of 6.

| Stage | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| Dense query embedding | 64.8 ms | 71.8 ms | 72.8 ms |
| Sparse query embedding | 0.34 ms | 0.43 ms | 0.55 ms |
| Rerank 20 → 6 | 1118.6 ms | 1172.5 ms | 1178.1 ms |
| Combined local model compute | 1183.9 ms | 1228.5 ms | 1243.4 ms |

The same run measured approximately `901.6 MiB` maximum RSS and `5.62 s` combined cold model
initialization. Cold initialization can include first-use model setup or downloads, so production
should keep the model cache persistent and should not use cold-start latency as the steady-state
request target.

This result demonstrates that the current interactive model path is viable without a GPU at the
certified two-CPU workload. It does **not** include Qdrant network/search latency or external LLM
latency; those are measured separately in the live deployment path.

## Release budgets

After obtaining measurement evidence, `config/performance_gate.toml` pins release budgets with
headroom above the observed p95 rather than tuning CI to a single runner sample:

| Guard | Certified budget |
| --- | ---: |
| Dense query p95 | ≤ 150 ms |
| Sparse query p95 | ≤ 10 ms |
| Rerank 20 → 6 p95 | ≤ 1650 ms |
| Combined local model compute p95 | ≤ 1750 ms |
| Process max RSS | ≤ 1536 MiB |

The CPU Performance workflow passes `config/performance_gate.toml` to `tractusmind-perf`. A workload
mismatch, p95 regression, or memory regression fails the workflow after writing the JSON evidence,
so a failed measurement remains inspectable.

## Measurement workflow

`.github/workflows/cpu-performance.yml` runs the production FastEmbed model stack on a Linux GitHub
runner and constrains the benchmark process to at most two CPUs using `taskset`. The CPU IDs are
derived from the runner's actual affinity rather than assuming that CPUs `0` and `1` are available.
The workload uses the existing full-corpus benchmark questions and the production candidate count
(`20`) and rerank limit (`6`). Representative candidate payloads are deterministic and
approximately 1,200 characters each so the cross-encoder receives a realistic small-document
workload without requiring a full Qdrant corpus rebuild.

The report records:

- cold dense query initialization,
- cold sparse query initialization,
- cold cross-encoder initialization,
- steady-state dense query p50/p95,
- steady-state sparse query p50/p95,
- steady-state rerank p50/p95 for 20 candidates to 6 results,
- combined model-compute p50/p95,
- process maximum RSS,
- CPU affinity and runtime metadata,
- release-budget checks and their observed/limit values.

The JSON report is uploaded as a 90-day GitHub Actions artifact even when a performance budget
fails.

## Production observability

The application already exports local-model Prometheus histograms:

- `tractusmind_model_load_duration_seconds{role=...}`
- `tractusmind_model_operation_duration_seconds{role=...,operation=...}`

Grafana should be used to watch the same model p95 signals in production. CI proves a deterministic
CPU baseline; live telemetry shows whether actual traffic, hosting contention, or model changes are
moving the system away from that baseline.

## Manual run

```bash
tractusmind-perf \
  --dataset benchmarks/full_corpus_v1.jsonl \
  --iterations 2 \
  --candidate-count 20 \
  --candidate-chars 1200 \
  --rerank-limit 6 \
  --budget config/performance_gate.toml \
  --output artifacts/cpu-performance.json
```

For a two-CPU Linux approximation matching the current API baseline, derive two CPUs from the
current process affinity and pass them to `taskset`; do not assume a hosted runner exposes CPU IDs
`0,1`.

Do not compare full-corpus ingestion duration with this benchmark. Ingestion can take many minutes
on CPU because thousands of document embeddings are generated once per changed source snapshot;
that work is not performed for every user question.
