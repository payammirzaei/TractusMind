# Reviewed production regressions

This directory is the code-reviewed destination for regression cases promoted through the
feedback-driven quality loop.

Use one file per benchmark contract:

```text
retrieval.jsonl
  -> tractusmind-benchmark --mode rerank

debug.jsonl
  -> tractusmind-benchmark --mode rerank with the debug retrieval lane

answer.jsonl
  -> tractusmind-answer-eval evaluate
```

The files are intentionally not created with placeholder cases. Export reviewed cases from the
protected quality operations API, inspect them, and commit only approved evidence expectations.

Example export calls:

```text
GET /v1/ops/quality/regressions/export?benchmark_kind=retrieval
GET /v1/ops/quality/regressions/export?benchmark_kind=debug
GET /v1/ops/quality/regressions/export?benchmark_kind=answer
```

A reviewed regression is a hard contract: once committed here, the production quality gate
requires it to pass. Raw feedback and unreviewed production interactions do not belong in this
directory.
