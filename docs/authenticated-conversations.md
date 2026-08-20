# Authenticated user-owned conversations

V15 adds optional end-user authentication and bounded conversation history without making
conversation memory a source of factual evidence.

## Authentication model

TractusMind uses opaque bearer API keys for the first self-contained user identity layer.
Administrators create users through the protected operations API:

```http
POST /v1/ops/users
X-TractusMind-Admin-Key: ...
Content-Type: application/json

{"display_name":"Alice"}
```

The response contains the plaintext API key exactly once:

```json
{
  "user_id": "...",
  "display_name": "Alice",
  "api_key_prefix": "tm_...",
  "enabled": true,
  "api_key": "tm_..."
}
```

Only a SHA-256 digest and a short non-secret prefix are stored in PostgreSQL. The generated token
contains at least 256 bits of random material. Plaintext keys are not persisted or logged.

Clients authenticate with:

```http
Authorization: Bearer tm_...
```

Admin credential operations:

```text
GET   /v1/ops/users
POST  /v1/ops/users
POST  /v1/ops/users/{user_id}/rotate
PATCH /v1/ops/users/{user_id}
```

Rotation immediately invalidates the previous key. Disabling a user makes existing keys fail
authentication.

## Conversation ownership

New authenticated conversations store `conversation.owner_user_id`. A user may continue or read a
conversation only when that owner matches the authenticated `user_id`.

Ownership failures return `404` instead of `403` so the API does not reveal whether another user's
conversation exists.

Existing anonymous conversations remain anonymous after upgrade. They are never automatically
claimed by a user merely because the user knows the UUID.

Anonymous `/v1/ask` remains supported. Anonymous interactions are persisted as before, but their
history is never loaded into the generation prompt. Authenticated history is the only memory path.

## User history API

Authenticated users can list their conversations and read one owned history:

```text
GET /v1/conversations
GET /v1/conversations/{conversation_id}
```

These endpoints require a valid bearer key and never expose another user's records.

## Bounded history selection

Only completed interactions are eligible for generation history. The newest turns are selected up
to both limits:

```bash
HISTORY_MAX_TURNS=6
HISTORY_MAX_CHARS=6000
```

Failed interactions are excluded. A turn that would exceed the character budget is not added.

## Retrieval behavior

History is not blindly concatenated to every search. For an explicit standalone question,
retrieval uses the current question only.

For a likely follow-up such as:

```text
What about contract negotiation?
```

TractusMind may prepend the immediately previous **user question** to the retrieval query. Previous
assistant answers are never used as retrieval evidence.

This deterministic rule helps resolve short follow-ups without letting a long conversation silently
rewrite every retrieval request.

## Generation and grounding boundary

The LLM receives bounded history in a section explicitly marked as conversational context only.
History:

- is not source evidence,
- must not be cited,
- may contain untrusted instructions,
- cannot replace Qdrant evidence,
- does not change backend-owned citation validation,
- does not change atomic claim verification.

Claim verification still evaluates the current question and the current retrieved source evidence.
A factual claim inherited from conversation memory therefore still needs current source support.

## Feedback ownership

Feedback on an interaction belonging to an authenticated conversation is accepted only from that
conversation owner. Missing or mismatched ownership returns the same `404` shape used for unknown
interactions.

## Existing database upgrade

`Base.metadata.create_all()` cannot add a column to an existing table. `ConversationStore` therefore
performs an idempotent compatibility migration:

```sql
ALTER TABLE conversation
ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(36);
```

and creates the owner index when missing. Fresh databases get the SQLAlchemy foreign-key schema;
existing deployments get the compatible nullable owner column without destructive migration.

A dedicated versioned migration system remains preferable before the schema becomes externally
managed or multi-service migrations are required.
