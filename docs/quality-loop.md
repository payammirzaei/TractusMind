# Feedback-driven quality loop

TractusMind turns selected production problems into reviewed regression cases without treating raw
user feedback as ground truth.

## Capture policy

Two signals create quality-review candidates automatically:

```text
failed answer interaction -> trigger=failure
user down-vote            -> trigger=feedback_down
```

Capture is idempotent per `(interaction_id, trigger)`. A repeated worker failure or repeated
negative feedback does not create duplicate review rows.

An up-vote does not create a review. If a user changes a previous down-vote to up, the existing
review remains auditable and shows the current feedback value so an operator can dismiss it.

## Human review gate

Every candidate starts as `pending`. Promotion is never automatic. An administrator must classify
one root cause:

```text
routing
retrieval
citation
generation
verification
source_data
versioning
other
```

The reviewer then either:

- dismisses the candidate, preserving the diagnosis and note, or
- promotes it into one immutable regression case.

Final review states are `dismissed` or `promoted`. A final review cannot be changed into a
contradictory decision. Repeating promotion of an already promoted review returns the existing
regression case idempotently.

## Regression case contract

A promoted case records:

```text
case_id
review_id
source interaction_id
benchmark kind: retrieval | debug | answer
question
expected source IDs
expected terms
expected abstention
route snapshot
root cause
reviewer note
created_at
```

For answerable cases, at least one expected source or expected term is required. Only answer
benchmarks can encode expected abstention.

## Operations API

All quality endpoints use the existing `X-TractusMind-Admin-Key` guard:

```text
GET  /v1/ops/quality/summary
GET  /v1/ops/quality/reviews
GET  /v1/ops/quality/reviews/{review_id}
POST /v1/ops/quality/reviews/{review_id}/decision
GET  /v1/ops/quality/regressions
GET  /v1/ops/quality/regressions/export
```

Useful filters:

```text
/v1/ops/quality/reviews?status=pending
/v1/ops/quality/reviews?root_cause=retrieval
/v1/ops/quality/regressions?benchmark_kind=debug
```

## Promotion example

```http
POST /v1/ops/quality/reviews/<review-id>/decision
X-TractusMind-Admin-Key: ...
Content-Type: application/json

{
  "action": "promote",
  "root_cause": "retrieval",
  "benchmark_kind": "retrieval",
  "expected_source_ids": ["tractusx-sdk"],
  "expected_terms": ["create_asset"],
  "reviewer_note": "Relevant SDK evidence was ranked below unrelated documentation."
}
```

## Benchmark export

`/regressions/export` returns NDJSON that matches the existing benchmark loaders.

Retrieval/debug export rows contain:

```json
{
  "id": "...",
  "category": "production-retrieval",
  "question": "...",
  "expected_sources": ["tractusx-sdk"],
  "expected_terms": ["create_asset"],
  "source_interaction_id": "..."
}
```

Answer benchmark rows additionally contain:

```json
{
  "answerable": false
}
```

The export remains an operator action. TractusMind does not append production cases directly to a
repository benchmark file because code review should remain the final gate before a regression
case becomes part of CI.

## Safety and quality rules

- Raw down-votes are signals, not labels.
- Raw provider exception messages are not copied into regression cases.
- Promotion requires explicit human root-cause classification.
- Promoted cases preserve their production interaction ID for traceability.
- A benchmark export is reproducible and can be code-reviewed before merging into `benchmarks/`.
- Quality-loop failures must never prevent a valid answer or feedback response from being returned.
