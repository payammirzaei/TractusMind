# Source update triggers

TractusMind uses a hybrid update model so knowledge does not stay stale when an allowlisted GitHub source changes.

## Immediate path: signed GitHub webhook

For repositories where you can manage webhooks, create a GitHub webhook with:

- Payload URL: `https://<TRACTUSMIND_DOMAIN>/v1/webhooks/github`
- Content type: `application/json`
- Secret: the exact value stored in `secrets/github_webhook_secret`
- Events: push events only
- Active: enabled

Generate the secret on the production host:

```bash
openssl rand -hex 32 > secrets/github_webhook_secret
chmod 644 secrets/github_webhook_secret
```

Start production with the webhook overlay in addition to the normal production/UI topology:

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  -f docker-compose.webhook.prod.yml \
  -f docker-compose.ui.prod.yml \
  up -d
```

GitHub signs every delivery with `X-Hub-Signature-256`. TractusMind verifies that HMAC against the raw request body before reading the event. `X-GitHub-Delivery` values are claimed in Redis for a bounded TTL so GitHub retries or duplicate deliveries do not fan out duplicate queue work. A queue failure releases the claim so a later GitHub retry can recover.

Push events are routed only when both the repository full name and pushed branch/tag match an enabled entry in `config/sources.toml`. The normal per-source Redis worker lock remains the second concurrency guard.

## Self-healing path: five-minute scheduler

Many Tractus-X sources are third-party Eclipse repositories where a TractusMind deployment cannot install a repository webhook. The scheduler therefore remains enabled and checks all configured sources every five minutes by default:

```text
SOURCE_SYNC_INTERVAL_SECONDS=300
```

The ingestion pipeline is incremental: unchanged files are not re-embedded. This polling path is also a safety net for webhook outages, missed deliveries, or temporarily unavailable edge routing.

## Expected behavior

```text
GitHub push
   |
   +--> webhook available? --> HMAC verify --> delivery dedupe --> matching source queue --> incremental sync
   |
   +--> webhook unavailable/missed ----------------------------------------------^
                                 scheduler fallback <= 5 min --------------------+
```

A push to an unrelated repository or to a branch/tag that is not the configured source ref is accepted but does not enqueue ingestion.
