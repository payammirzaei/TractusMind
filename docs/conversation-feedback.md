# Conversation, answer trace, and feedback persistence

TractusMind persists completed and failed answer interactions in PostgreSQL so production behavior
can be evaluated from real usage instead of only offline benchmark seeds.

## Data model

Three tables are used:

- `conversation`: groups related requests by an opaque UUID.
- `answer_interaction`: immutable request/answer and execution-trace record.
- `answer_feedback`: one mutable feedback record per completed interaction.

A completed interaction stores:

```text
interaction_id
conversation_id
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

Failed answer requests are also persisted with `status=failed`, the captured stage durations,
total duration, trace ID when tracing is enabled, and a safe `error_type`. Raw provider exception
messages are not persisted in this table.

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

A later request can continue the same grouping:

```json
{
  "question": "What about contract negotiation?",
  "conversation_id": "..."
}
```

Conversation grouping does not yet inject previous conversation turns into the generation prompt.
That will only be added with an explicit history-selection and token-budget policy; persistence and
LLM context are intentionally separate concerns.

## Request-scoped timing trace

`observe_stage()` still records Prometheus histograms and OpenTelemetry spans. It additionally
records exact durations in a request-local `contextvars` collector. The `/v1/ask` route persists
that collector with the final interaction.

Typical persisted stage data:

```json
{
  "retrieval": 0.184,
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

## Admin inspection

Conversation history is not exposed through a public read endpoint because TractusMind does not
yet have user authentication or ownership checks. Administrators can inspect production records
through the existing protected operations API:

```text
GET /v1/ops/interactions
GET /v1/ops/interactions?status=failed
GET /v1/ops/interactions?conversation_id=<uuid>
GET /v1/ops/feedback/summary
```

These endpoints use the same `X-TractusMind-Admin-Key` protection as the ingestion operations API.

## Failure policy

Answer persistence is deliberately best-effort. A valid grounded or abstained answer is not turned
into an HTTP failure merely because the analytics database write failed. In that case the response
is returned without persisted interaction identifiers and a structured persistence error is
logged.

Generation/runtime failures are also persisted on a best-effort basis before the normal HTTP error
is returned.

## Next use of this data

The persisted interaction corpus is intended to feed:

- feedback-segmented quality reports,
- regression-case promotion from real failed/down-voted questions,
- route and citation error analysis,
- latency/bottleneck analysis,
- later conversation history selection,
- benchmark expansion from reviewed production examples.

Raw production feedback should never be promoted automatically into a gold benchmark without
review.
