# Production evaluation gate

TractusMind separates benchmark **measurement** from benchmark **enforcement**.

Seed datasets are useful for trend reporting, but aggregate recall/MRR thresholds are not invented
before a full-corpus baseline exists. The production gate therefore starts with hard product
contracts that do not require arbitrary tuning.

## Enforced contracts

`config/quality_gate.toml` currently enforces:

```text
unsafe answer rate                = 0
unsafe evidence acceptance rate   = 0
all reviewed retrieval regressions pass
all reviewed debug regressions pass
all reviewed answer regressions pass
```

A promoted production regression is treated as a hard contract because a human reviewer already
approved its expected behavior.

Seed retrieval/debug metrics are still recorded as artifacts so future baseline changes can be
measured before aggregate thresholds are introduced.

## Live workflow

`.github/workflows/quality-gate.yml` runs the real production retrieval and answer paths against a
configured Qdrant corpus and LLM provider.

Scheduled execution is opt-in:

```text
Repository variable:
QUALITY_GATE_ENABLED=true
```

Required GitHub Actions configuration:

```text
Secret: QUALITY_QDRANT_URL
Secret: QUALITY_QDRANT_API_KEY        # optional when Qdrant has no auth
Secret: QUALITY_LLM_BASE_URL
Secret: QUALITY_LLM_API_KEY
Variable: QUALITY_LLM_MODEL
```

The workflow can always be started manually with `workflow_dispatch`. Missing required live
configuration fails explicitly instead of silently switching to mocks.

## Reports

A run uploads JSON artifacts for:

```text
retrieval seed benchmark
debug seed benchmark
threshold calibration
grounded answer safety evaluation
reviewed retrieval regressions, when present
reviewed debug regressions, when present
reviewed answer regressions, when present
final quality-gate verdict
```

Reports are retained as GitHub Actions artifacts so a failure can be inspected without rerunning
the model pipeline.

## Threshold calibration and pinning

Calibration runs with:

```bash
tractusmind-answer-eval calibrate \
  --dataset benchmarks/answer_v0.jsonl \
  --max-unsafe-rate 0
```

The gate refuses production enforcement with `--require-pinned-threshold` until the measured
threshold has been reviewed and committed to:

```toml
[calibration]
threshold_tolerance = 0.000001
minimum_relevance_score = <measured value>
```

A later calibration that recommends a different threshold beyond the configured tolerance fails
with `threshold-drift`. This prevents a new corpus/model/index from silently changing the
production evidence cutoff.

The threshold is intentionally not populated by code generation or guessed from seed data. It must
come from a real corpus calibration run.

## Reviewed regressions

Approved quality-loop exports belong in:

```text
benchmarks/regressions/retrieval.jsonl
benchmarks/regressions/debug.jsonl
benchmarks/regressions/answer.jsonl
```

The workflow skips a regression kind when its file does not exist or is empty. Once a reviewed
case is committed, every case in that file must pass.

## Local gate usage

After producing reports:

```bash
tractusmind-quality-gate \
  --config config/quality_gate.toml \
  --calibration artifacts/quality/calibration.json \
  --answer artifacts/quality/answer-seed.json \
  --require-pinned-threshold
```

Add regression report arguments when those datasets exist:

```text
--retrieval-regression <report.json>
--debug-regression <report.json>
--answer-regression <report.json>
```

The command prints a JSON verdict and exits non-zero when any enforced contract fails.

## What is not gated yet

Aggregate seed-dataset recall, MRR, NDCG, false-abstention rate, and latency are measured but are
not yet assigned arbitrary pass/fail numbers. After a full-corpus baseline and several measured
runs exist, versioned lower/upper bounds can be added with evidence for why those numbers are safe.
