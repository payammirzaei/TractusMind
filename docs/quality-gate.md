# Production evaluation gate

TractusMind separates **measurement** from **enforcement**.

V20 adds a full-corpus contract before any retrieval or answer metric is considered valid. The gate
therefore verifies the indexed source set and upstream freshness before evaluating the model path.

## Enforced contracts

`config/quality_gate.toml` currently enforces:

```text
unsafe answer rate                = 0
unsafe evidence acceptance rate   = 0
all reviewed retrieval regressions pass
all reviewed debug regressions pass
all reviewed answer regressions pass
pinned evidence threshold does not drift
```

A reviewed production regression is a hard contract because a human reviewer explicitly approved
its expected behavior.

Aggregate recall/MRR/NDCG are measured and recorded, but are not given invented pass/fail numbers
before repeated full-corpus measurements justify them.

## Full-corpus prerequisite

Before the production gate runs benchmarks it executes:

```bash
tractusmind-corpus-validate --verify-upstream
```

For every enabled source this requires PostgreSQL source state, a matching successful ingestion run,
Qdrant chunks for the same snapshot, no stale snapshot chunks, and equality with the current GitHub
commit resolved from the configured ref.

See [`full-corpus-validation.md`](full-corpus-validation.md) for the complete corpus contract.

## Production quality workflow

`.github/workflows/quality-gate.yml` runs weekly when enabled or manually through
`workflow_dispatch`.

Required GitHub environment: `quality`.

### Secrets

```text
QUALITY_DATABASE_URL
QUALITY_QDRANT_URL
QUALITY_QDRANT_API_KEY        # optional when Qdrant has no auth
QUALITY_GITHUB_TOKEN
QUALITY_LLM_BASE_URL
QUALITY_LLM_API_KEY
```

### Variables

```text
QUALITY_LLM_MODEL
QUALITY_QDRANT_COLLECTION     # optional; defaults to tractusmind_knowledge
QUALITY_GATE_ENABLED
```

Missing live configuration fails explicitly. The workflow never falls back to mocks.

## V20 benchmark sets

The enforced live path now uses:

```text
benchmarks/full_corpus_v1.jsonl   # retrieval; all six enabled sources
benchmarks/debug_v0.jsonl         # exact/debug retrieval cases
benchmarks/answer_v1.jsonl        # all six sources + negative abstention cases
```

The V1 retrieval and answer datasets are tested against `config/sources.toml`: every enabled source
must have benchmark coverage.

## Threshold calibration and pinning

Full-corpus calibration runs with:

```bash
tractusmind-answer-eval calibrate \
  --dataset benchmarks/answer_v1.jsonl \
  --max-unsafe-rate 0
```

The dedicated `.github/workflows/full-corpus-validation.yml` workflow measures the candidate
threshold and evaluates answers at that measured value. It emits a `pin-candidate.toml` artifact but
never commits or applies the value automatically.

After reviewing the corpus manifest, source commits, model identities, retrieval results, answer
metrics, and safety/regression verdict, commit the reviewed value to:

```toml
[calibration]
threshold_tolerance = 0.000001
minimum_relevance_score = <reviewed measured value>
```

The production quality gate runs with `--require-pinned-threshold`. If a future full-corpus
calibration recommends a value outside the configured tolerance, it fails with `threshold-drift`.

## Reviewed regressions

Human-approved production cases live in:

```text
benchmarks/regressions/retrieval.jsonl
benchmarks/regressions/debug.jsonl
benchmarks/regressions/answer.jsonl
```

A regression kind is skipped only while its file is absent or empty. Once cases are committed, every
reviewed case must pass.

## Reports

The production workflow retains 90-day artifacts for:

```text
corpus.json
retrieval-full.json
debug.json
calibration.json
answer-full.json
reviewed regression reports when present
gate.json
```

The separate full-corpus measurement workflow additionally records source-sync output,
`validation-summary.json`, input SHA-256 values, source/upstream commits, and `pin-candidate.toml`.

## Local gate usage

After reports are generated:

```bash
tractusmind-quality-gate \
  --config config/quality_gate.toml \
  --calibration artifacts/quality/calibration.json \
  --answer artifacts/quality/answer-full.json \
  --require-pinned-threshold
```

Add reviewed regression reports when present:

```text
--retrieval-regression <report.json>
--debug-regression <report.json>
--answer-regression <report.json>
```

The command prints a JSON verdict and exits non-zero when an enforced contract fails.

## Deliberate limits

- A threshold is never guessed or auto-committed.
- Raw feedback never becomes a regression benchmark automatically.
- A stale or incomplete corpus cannot produce a valid full-corpus quality run.
- Aggregate retrieval metric thresholds remain report-only until repeated measurements justify a
  versioned baseline.
- LLM evaluation can vary by provider/model behavior, so every full-corpus evidence packet records
  the exact model identity and Git/source inputs used.
