# Full-corpus validation and calibration

V20 turns TractusMind quality measurement into a reproducible, source-complete process. A benchmark
run is not considered a valid full-corpus measurement unless the indexed corpus itself passes the
corpus contract first.

## Corpus contract

Run:

```bash
tractusmind-corpus-validate --verify-upstream
```

For every enabled source in `config/sources.toml`, the command requires:

1. PostgreSQL has a successful `source_state`.
2. Repository, component, and configured ref match the registry.
3. `last_successful_run_id` resolves to a succeeded ingestion run.
4. The run snapshot equals `source_state.snapshot_commit_sha`.
5. Qdrant contains chunks for exactly that successful snapshot.
6. No chunks from older snapshots remain for that source.
7. With `--verify-upstream`, the indexed snapshot equals the current GitHub commit resolved from the
   configured ref.

The JSON report records the registry SHA-256, model-scoped collection name, dense/sparse/reranker
identities, file/chunk counts, source snapshot commits, upstream commits, and all violations.

A DB/Qdrant pair that is internally consistent but behind upstream therefore fails freshness
validation rather than producing a misleading benchmark result.

## V1 benchmark sets

`benchmarks/full_corpus_v1.jsonl` has evidence coverage for every enabled source:

- `tractusx-sdk`
- `tractusx-edc`
- `digital-twin-registry`
- `semantic-models`
- `tractusx-docs`
- `tractusx-release`

`benchmarks/answer_v1.jsonl` likewise covers all six sources with answerable cases and retains
unanswerable cases for abstention/safety calibration.

CI has a deterministic test that requires both V1 datasets to cover the complete enabled source
set. Adding a new enabled source without adding benchmark coverage is therefore a test failure.

## Dedicated quality environment

The full-corpus workflow is `.github/workflows/full-corpus-validation.yml`. It should point to a
**dedicated quality environment**, not casually at production state.

Configure GitHub environment `quality` with:

### Secrets

```text
QUALITY_DATABASE_URL
QUALITY_QDRANT_URL
QUALITY_QDRANT_API_KEY        # optional only when the Qdrant environment has no API key
QUALITY_GITHUB_TOKEN
QUALITY_LLM_BASE_URL
QUALITY_LLM_API_KEY
```

### Variables

```text
QUALITY_LLM_MODEL
QUALITY_QDRANT_COLLECTION     # optional; defaults to tractusmind_knowledge
FULL_CORPUS_VALIDATION_ENABLED
QUALITY_GATE_ENABLED
```

The workflow bootstraps the quality PostgreSQL schema. When `refresh_corpus=true`, it runs
incremental synchronization for every enabled source before validation.

## Measurement sequence

```text
quality DB schema bootstrap
        ↓
all enabled source IDs
        ↓
incremental sync each source
        ↓
corpus contract + upstream freshness
        ↓
dense / hybrid / rerank benchmark
        ↓
debug rerank benchmark
        ↓
zero-unsafe evidence calibration
        ↓
measured threshold
        ↓
answer evaluation at measured threshold
        ↓
reviewed regression evaluation
        ↓
safety/regression candidate gate
        ↓
validation-summary.json + pin-candidate.toml
```

The measured threshold is loaded into a **subsequent workflow step** before answer evaluation. This
matters because values written to GitHub Actions `GITHUB_ENV` are not visible earlier in the same
step.

## Validation evidence

The workflow uploads a 90-day artifact named:

```text
tractusmind-full-corpus-<git-sha>
```

Important files include:

```text
corpus.json
retrieval.json
debug.json
calibration.json
answer.json
candidate-gate.json
validation-summary.json
pin-candidate.toml
sync/<source-id>.json
```

`validation-summary.json` binds the measurement to:

- application Git SHA
- exact source snapshot commits and upstream commits
- registry SHA-256
- model-scoped Qdrant collection
- dense, sparse, reranker, and LLM identities
- SHA-256 hashes of benchmark/config inputs
- measured retrieval and answer metrics
- measured minimum relevance threshold

This is the evidence packet used when reviewing a calibration change.

## Pinning the measured threshold

The workflow never commits a threshold automatically. Raw measurement is not authority to mutate
production behavior.

After reviewing the full-corpus artifact, copy the measured value from `pin-candidate.toml` into
`config/quality_gate.toml`:

```toml
[calibration]
threshold_tolerance = 0.000001
minimum_relevance_score = <reviewed measured value>
```

Commit that change through normal code review.

After the threshold is pinned, `.github/workflows/quality-gate.yml` runs the V1 six-source corpus
contract, freshness check, calibration, grounded answer evaluation, and reviewed regressions. It
uses `--require-pinned-threshold`, so calibration drift beyond the configured tolerance fails the
production quality gate.

## What is not automatic

- The workflow does not silently update `quality_gate.toml`.
- The workflow does not promote raw feedback into benchmarks.
- It does not claim a run is full-corpus when any enabled source is missing or stale.
- It does not make aggregate retrieval metrics hard gates before a measured baseline has been
  reviewed.
- It does not make LLM evaluation perfectly deterministic; model/provider identity is recorded so
  changes are inspectable.

## Operational recommendation

Run full-corpus validation after meaningful changes to any of these:

- source registry or allowlists
- chunking
- embedding or sparse models
- Qdrant payload/index strategy
- retrieval fusion
- reranker model or weights
- routing
- evidence threshold behavior
- generation or verification provider/model

The scheduled monthly measurement can be enabled with `FULL_CORPUS_VALIDATION_ENABLED=true`.
The weekly production gate can be enabled separately with `QUALITY_GATE_ENABLED=true` after a
reviewed threshold has been pinned.
