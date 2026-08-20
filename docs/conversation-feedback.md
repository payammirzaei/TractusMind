# Conversation, answer trace, and feedback persistence

TractusMind persists completed and failed answer interactions in PostgreSQL so production behavior
can be evaluated from real usage instead of only offline benchmark seeds.

## Data model

Three conversation/feedback tables are used:

- `conversation`: groups related requests by an opaque UUID and may carry `owner_user_id`.
- `answer_interaction`: immutable request/answer and execution-trace record.
- `answer_feedback`: one mutable feedback record per completed interaction.

Authenticated user identity is stored separately in `app_user`; plaintext API keys are never stored.

A completed interaction stores:

```text
interaction_id
conversation_id
request_id
question
answer
grounded / abstained
evidence_count
model
intent + full route JSON
citations
verification report
stage durations
total duration
OpenTelemetry trace_id
created_at
```

`request_id` is the same bounded value returned in `X-Request-ID`, so logs can be correlated with
the persisted interaction even when OpenTelemetry export is disabled. Client-supplied request IDs
are accepted only when non-empty and no longer than 64 characters; otherwise TractusMind creates a
UUID.

Failed answer requests are also persisted with `status=failed`, the captured stage durations,
total duration, request/trace correlation, a safe `error_type`, and route/model/evidence metadata
when the pipeline reached those stages. Raw provider exception messages are not persisted in this
table.

## Conversation continuity

The first request may omit a conversation ID:

```http
POST /v1/ask
Content-Type: application/json

{
  "question": "How do I create an asset with the SDK?"
}
```

A successful persisted response includes both identifiers:

```json
{
  "interaction_id": "...",
  "conversation_id": "..."
}
```

An authenticated user can continue their owned conversation:

```http
Authorization: Bearer tm_...
Content-Type: application/json

{
  "question": "What about contract negotiation?",
  "conversation_id": "..."
}
```

Authenticated owned conversations may contribute bounded completed history to generation.
Anonymous requests remain supported, but anonymous history is never injected into the prompt.

History is limited by `HISTORY_MAX_TURNS` and `HISTORY_MAX_CHARS`. It is explicitly marked as
conversation context, not source evidence, and must never be cited. Claim verification continues to
use the current question and current retrieved source evidence.

See [`authenticated-conversations.md`](authenticated-conversations.md) for ownership, credential,
and follow-up retrieval rules.

## Request-scoped timing trace

`observe_stage()` still records Prometheus histograms and OpenTelemetry spans. It additionally
records exact durations in a request-local `contextvars` collector. The `/v1/ask` route persists
that collector with the final interaction.

Local model operations also write detail keys such as `model.dense.query`,
`model.sparse.query`, or reranker operation names when those model services are instrumented.

Typical persisted stage data:

```json
{
  "retrieval": 0.184,
  "model.dense.query": 0.031,
  "model.sparse.query": 0.018,
  "generation": 0.923,
  "verification": 0.417
}
```

This makes one production answer inspectable without reconstructing latency from aggregate
Prometheus buckets.

## Feedback

Clients can submit or update feedback for a completed interaction:

```http
POST /v1/feedback
Content-Type: application/json

{
  "interaction_id": "...",
  "rating": "down",
  "reason": "citation",
  "comment": "The cited source does not support the exact claim."
}
```

`rating` is `up` or `down`. `reason` and `comment` are optional. A second submission for the same
interaction updates the existing feedback instead of creating contradictory duplicate votes.
Feedback for unknown or failed interactions is rejected.

If the interaction belongs to an authenticated conversation, feedback is accepted only from that
conversation owner. Cross-user and unknown interaction cases intentionally share the same `404`
shape.

## User-owned reads and admin inspection

Authenticated users can read only their own conversation history:

```text
GET /v1/conversations
GET /v1/conversations/{conversation_id}
```

Administrators retain protected cross-user production inspection through:

```text
GET /v1/ops/interactions
GET /v1/ops/interactions/{interaction_id}
GET /v1/ops/interactions?status=failed
GET /v1/ops/interactions?conversation_id=<uuid>
GET /v1/ops/feedback/summary
```

Admin endpoints use `X-TractusMind-Admin-Key`. User history endpoints use the opaque bearer user
credential. The interaction response includes both `request_id` and `trace_id`, enabling direct
correlation from structured logs or an OpenTelemetry backend.

## Failure policy

Answer persistence is deliberately best-effort. A valid grounded or abstained answer is not turned
into an HTTP failure merely because the analytics database write failed. In that case the response
is returned without persisted interaction identifiers and a structured persistence error is
logged.

Generation/runtime failures are also persisted on a best-effort basis before the normal HTTP error
is returned.

## Quality use of persisted interactions

The persisted interaction corpus feeds:

- feedback-segmented quality reports,
- human-reviewed regression-case promotion from failed/down-voted questions,
- route and citation error analysis,
- latency/bottleneck analysis,
- authenticated bounded conversation context,
- benchmark expansion from reviewed production examples.

Raw production feedback is never promoted automatically into a gold benchmark without review.
