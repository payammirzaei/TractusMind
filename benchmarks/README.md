# TractusMind Benchmarks

This directory contains fixed evaluation sets used to prevent retrieval and answer-quality regressions.

## Retrieval benchmark

`dense_v0.jsonl` contains source-grounded retrieval questions. Each case declares expected source IDs and optional terms that must appear in a returned chunk.

```bash
tractusmind-benchmark --mode all --k 5
```

The retrieval runner compares Dense, Hybrid, and Hybrid + Reranker with Recall@K, MRR, NDCG@K, first relevant rank, and top source IDs.

## Debug retrieval benchmark

`debug_v0.jsonl` contains validated code/config identifiers from current Tractus-X sources. It exercises the debug-specific path: exact phrase/symbol/path lookup + hybrid retrieval + weighted RRF + cross-encoder reranking.

```bash
tractusmind-benchmark \
  --dataset benchmarks/debug_v0.jsonl \
  --mode rerank \
  --k 5
```

The first seed covers real identifiers including `BaseConnectorService`, `edc.api.auth.key`, `DspTransferProcessTransformV08Extension`, `ShellMapper`, and `AssetAdministrationShellApiDelegate`.

## Answer benchmark

`answer_v0.jsonl` contains both answerable and deliberately unanswerable questions. The negative cases are required for meaningful abstention calibration.

Calibrate the reranker evidence cutoff without calling the LLM:

```bash
tractusmind-answer-eval calibrate --max-unsafe-rate 0
```

Then, with an LLM provider configured, run the end-to-end answer gate:

```bash
tractusmind-answer-eval evaluate
```

The answer runner reports:

- grounded answer accuracy
- citation correctness
- claim support rate
- false abstention rate
- unsafe answer rate

Calibration reports a recommended `MINIMUM_RELEVANCE_SCORE` plus true accept, false abstention, unsafe evidence accept, and balanced accuracy metrics.
