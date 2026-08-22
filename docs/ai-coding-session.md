# AI-Assisted Engineering Session Log

## Production ingestion reliability in TractusMind

**Repository:** [payammirzaei/TractusMind](https://github.com/payammirzaei/TractusMind)  
**Primary implementation:** [PR #25 — event-driven GitHub ingestion](https://github.com/payammirzaei/TractusMind/pull/25)  
**Related production incidents:** [PR #20](https://github.com/payammirzaei/TractusMind/pull/20), [PR #21](https://github.com/payammirzaei/TractusMind/pull/21), [PR #22](https://github.com/payammirzaei/TractusMind/pull/22)  
**AI coding workflow:** ChatGPT-assisted engineering with repository inspection, implementation review, testing, CI feedback, and iterative hardening.

> **Disclosure:** This is a curated engineering log of a real AI-assisted development workflow, reconstructed from the merged code, commits, PR descriptions, tests, and production fixes. It is not presented as a verbatim chat transcript. The purpose is to show how I use an AI coding assistant to reason about architecture, challenge implementation details, test assumptions, and ship production code.

---

## 1. Problem

TractusMind continuously ingests allowlisted Tractus-X repositories into a grounded AI knowledge system. The original scheduler-based approach was safe but could leave knowledge stale for hours.

The goal was not simply to "add a webhook". The production requirement was:

- react quickly to source changes;
- authenticate incoming events;
- avoid duplicate background jobs;
- preserve retries after transient failures;
- route only configured repositories and refs;
- keep third-party repositories working when no webhook can be installed;
- keep expensive ingestion away from the request path;
- prove the behavior through tests and the real HTTPS production edge.

This turned a small feature request into a distributed-systems problem involving **FastAPI, Redis, Dramatiq, GitHub webhooks, HMAC verification, idempotency, queues, retries, concurrency guards, Docker, Caddy, and CI smoke tests**.

---

## 2. How I used the AI assistant

I use AI as an engineering partner, not as an autocomplete replacement. My normal loop is:

```text
problem
  -> inspect current architecture
  -> identify failure modes
  -> propose smallest durable design
  -> implement
  -> add adversarial/regression tests
  -> run CI / production-style smoke
  -> inspect failure
  -> revise design
  -> merge only when the operational contract is proven
```

The important part is that I keep ownership of the decisions. I ask the assistant to expose assumptions and edge cases, then I choose the trade-off and verify it against the real system.

---

## 3. Session log

### Step 1 — Define the production behavior

**Human intent, summarized:** Make source ingestion near-real-time, but do not replace a reliable scheduler with a fragile event-only design.

**AI-assisted analysis:** We separated the problem into an immediate path and a self-healing path.

The resulting architecture became:

```text
GitHub push
   |
   +--> webhook available?
   |       |
   |       +--> HMAC verify
   |       +--> delivery dedupe
   |       +--> repository/ref match
   |       +--> enqueue background sync
   |
   +--> webhook unavailable / delivery missed
           |
           +--> five-minute scheduler fallback
```

**Decision I kept:** use a **hybrid event-driven + polling model** rather than pretending webhooks are perfectly reliable or available for every third-party repository.

Why: TractusMind indexes repositories that I do not own. A pure webhook architecture would create a hidden availability dependency on external configuration I cannot control.

---

### Step 2 — Authenticate before parsing

A public webhook endpoint creates a new attack surface. The request body must be authenticated exactly as GitHub sent it.

The implementation verifies `X-Hub-Signature-256` over the **raw request body** using HMAC-SHA256:

```python
def verify_github_signature(*, body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
```

**Engineering choice:** constant-time comparison with `hmac.compare_digest`, and verification before trusting the JSON payload.

**Why it matters:** signature verification should protect the actual bytes received, not a parsed/re-serialized approximation of them.

---

### Step 3 — Treat duplicate delivery as normal

GitHub can retry webhook deliveries. A production system must assume duplicate delivery, not treat it as an exceptional case.

We use the GitHub delivery ID as a bounded Redis idempotency claim:

```python
claimed = await redis.set(
    delivery_key,
    "1",
    ex=delivery_ttl_seconds,
    nx=True,
)
```

If the claim already exists, the endpoint returns an accepted duplicate response without enqueueing more work.

```text
same delivery ID
      |
      +--> first request  -> claim -> queue
      |
      +--> replay/retry   -> duplicate -> no second queue job
```

**Decision I kept:** dedupe at the webhook boundary **and** retain the existing per-source Redis worker lock.

The two controls solve different races:

- delivery dedupe prevents one GitHub event from fanning out repeatedly;
- the source lock prevents multiple independent triggers from synchronizing the same source concurrently.

That is intentionally defense in depth rather than one overloaded locking mechanism.

---

### Step 4 — Make failure retryable

The first obvious idempotency implementation has a dangerous edge case: claim the delivery ID, fail while enqueueing, and permanently suppress GitHub's later retry.

The corrected behavior releases the claim when the queue operation fails:

```python
try:
    sync_source_task.send(source.id)
except Exception:
    await redis.delete(delivery_key)
    raise
```

**This was one of the most important design details in the session.**

Idempotency without recovery can become silent data loss.

The contract we wanted was:

```text
accepted + queued       -> keep claim
accepted duplicate      -> keep claim
invalid payload         -> release claim where retry can help
queue infrastructure failure -> release claim
```

This is the kind of edge case I specifically use AI review for: not "does the happy path work?", but "what state survives when line N throws?"

---

### Step 5 — Route only the intended source

A valid GitHub signature does not mean every valid GitHub event should trigger work.

The event is matched against the configured source registry by:

1. provider;
2. enabled status;
3. normalized `owner/repository`;
4. exact configured branch or tag ref.

```python
return [
    source
    for source in sources
    if source.enabled
    and source.provider.casefold() == "github"
    and normalize_github_repository(source.full_name) == repository
    and ref_matches_source(push_ref, source.ref)
]
```

This keeps the webhook generic while the registry remains the source of truth.

**Design principle:** integrations should not bypass existing domain rules just because they arrive through a new transport.

---

### Step 6 — Keep ingestion asynchronous

The webhook returns `202 Accepted`; it does not run indexing inside the HTTP request.

```text
FastAPI webhook
    |
    +--> validate
    +--> dedupe
    +--> route
    +--> Dramatiq enqueue
               |
               +--> worker performs source synchronization
```

That preserves a short request lifecycle while CPU-heavy fetching, chunking, embedding, and Qdrant writes remain in the background worker.

This is important because real Tractus-X sources can be large enough for ingestion to run for tens of minutes.

---

## 4. Production incident: "works locally" was not enough

The webhook feature sits on top of ingestion code that had already been hardened through real production failures.

### Incident A — repository-sized indexing stalled

A full source sync could stall after FastEmbed initialization on constrained production workers.

Instead of adding a bigger machine first, I traced the stage boundary and changed hybrid indexing from one repository-sized logical operation to bounded batches.

**PR:** [#20 — prevent production ingestion stalls](https://github.com/payammirzaei/TractusMind/pull/20)

The resulting behavior:

```text
70 chunks
   -> 32
   -> 32
   -> 6
```

A regression test proves the exact batching contract.

This also added stage-level structured logging so a future stall is observable as fetch/chunk/dense/sparse/upsert progress rather than "worker is still running".

---

### Incident B — telemetry lied by omission

An active ingestion run appeared as `0 chunks / 0 indexed` until completion, while interrupted workers could leave zombie `RUNNING` rows.

**PR:** [#21 — live ingestion telemetry and stale-run cleanup](https://github.com/payammirzaei/TractusMind/pull/21)

I changed the state model so progress is persisted during execution:

```text
plan -> fetched -> chunked -> indexed batch 1 -> indexed batch 2 -> ... -> complete
```

The retrieval service accepts an asynchronous progress callback and persists index counts after every Qdrant batch.

A new source run also marks an older unfinished run as interrupted rather than leaving misleading operational state.

**Lesson:** observability is part of correctness when operators make decisions from the state you expose.

---

### Incident C — default worker timeout killed valid jobs

A clean full-corpus source sync consistently died around ten minutes even though the pipeline itself was progressing normally.

The root cause was Dramatiq's default actor time limit, not the application algorithm.

**PR:** [#22 — allow full-corpus ingestion to exceed the default limit](https://github.com/payammirzaei/TractusMind/pull/22)

The fix gives source sync a bounded four-hour budget while keeping the normal retry policy:

```python
SOURCE_SYNC_TIME_LIMIT_MS = 4 * 60 * 60 * 1000

@dramatiq.actor(max_retries=3, time_limit=SOURCE_SYNC_TIME_LIMIT_MS)
def sync_source_task(source_id: str):
    ...
```

A regression test inspects the actor configuration directly so the production contract cannot silently regress.

**Lesson:** before optimizing code, confirm which layer is actually terminating it.

---

## 5. Tests I expected before calling the feature done

The AI-assisted implementation was not complete when the endpoint returned `202`.

I wanted tests for the failure boundaries:

### Unit behavior

- accepts a valid SHA-256 GitHub signature;
- rejects missing or tampered signatures;
- routes only matching repository + ref;
- supports branch and tag refs;
- ignores disabled sources.

### Production smoke behavior

The hardened runtime test goes through the real HTTPS edge and verifies:

1. signed webhook is accepted;
2. replaying the same delivery ID is identified as duplicate;
3. invalid signature is rejected with `401`;
4. Mission Control authentication still works after the production topology change.

This matters because a unit test cannot prove that Caddy is routing the raw webhook request to FastAPI correctly.

---

## 6. Deployment trade-off

The application already had a hardened production topology. I did not want webhook support to become a mandatory secret/configuration requirement that breaks existing deployments.

So the webhook secret is an **opt-in production overlay**:

```text
docker-compose.prod.yml
+ docker-compose.webhook.prod.yml   # only when webhook ingestion is enabled
+ docker-compose.ui.prod.yml
```

If it is not configured, the endpoint fails closed and the scheduler remains functional.

**Trade-off:** slightly more deployment configuration, but no surprise breaking change for an installation that cannot or does not want to expose GitHub webhook ingestion.

---

## 7. Observability

A successful enqueue increments a labeled queue metric:

```python
QUEUE_ENQUEUED.labels(origin="github_webhook").inc()
```

Structured logs record repository, ref, delivery ID, and queued source IDs.

Failures use exception logging and preserve enough context to investigate the event without logging the webhook secret.

This makes the integration answerable in production:

- Did GitHub reach us?
- Was the signature accepted?
- Was it a duplicate?
- Which source matched?
- Was work queued?
- Did the worker start?
- Which ingestion stage is active?
- How many chunks have been indexed?

---

## 8. What the AI assistant was useful for

The highest-value uses were not generating boilerplate. They were:

### Architecture pressure-testing

I used the assistant to compare event-only, polling-only, and hybrid designs and to look for ownership/availability assumptions.

### Failure-mode review

Questions like:

- What happens if Redis accepts the idempotency claim but queue enqueue fails?
- Can two different webhook deliveries still synchronize the same source concurrently?
- Does a valid webhook for the wrong ref trigger ingestion?
- Can production routing modify the request body before signature verification?
- What happens for repositories where I cannot install a webhook?

These questions materially changed the design.

### Debugging across layers

The ingestion incidents required separating:

```text
HTTP/API
queue
worker runtime
embedding runtime
Qdrant writes
persistent run state
CI / production edge
```

AI helped accelerate hypothesis generation, but each hypothesis had to match logs, code, and a reproducible test before I accepted it.

### Regression design

For every production failure I try to leave behind a small automated contract that would have caught it earlier.

That is why the project now has tests for batching, progress callbacks, actor time limits, webhook signatures, source routing, duplicate delivery, and hardened HTTPS behavior.

---

## 9. Where I disagreed with the easy implementation

The easiest implementation would have been:

```text
POST webhook
 -> parse JSON
 -> enqueue repo
 -> return 200
```

I rejected that because it ignores the behavior that actually matters in production.

The final implementation adds:

- raw-body HMAC verification;
- constant-time comparison;
- bounded Redis delivery dedupe;
- retry-safe claim release;
- exact repository/ref routing;
- existing source-level concurrency lock;
- asynchronous Dramatiq execution;
- five-minute self-healing scheduler fallback;
- opt-in production secret handling;
- real HTTPS smoke coverage;
- structured logs and queue metrics.

The extra code exists because the failure modes are real, not because the architecture needed to look sophisticated.

---

## 10. Result

The merged implementation makes TractusMind source updates **near-real-time where webhooks are available** while keeping a **self-healing polling fallback** for external repositories.

More importantly, it has explicit behavior for duplicate delivery, queue failure, concurrency, invalid signatures, wrong refs, missed webhooks, long-running ingestion, partial progress, and production routing.

**Primary evidence:** [PR #25](https://github.com/payammirzaei/TractusMind/pull/25)

Related reliability work:

- [PR #20 — bounded indexing + stage observability](https://github.com/payammirzaei/TractusMind/pull/20)
- [PR #21 — live progress + interrupted-run cleanup](https://github.com/payammirzaei/TractusMind/pull/21)
- [PR #22 — explicit long-running worker time budget](https://github.com/payammirzaei/TractusMind/pull/22)

---

## 11. What this session says about how I build

I am comfortable letting AI move quickly through implementation detail, but I do not delegate engineering judgment to it.

My responsibility is to decide:

- what must be true in production;
- where state lives;
- which failures can be retried safely;
- what needs to be idempotent;
- which assumptions should fail closed;
- what belongs on the request path versus a worker;
- what evidence is strong enough to merge.

The code is the output. The real work is turning ambiguous operational behavior into explicit, tested contracts.