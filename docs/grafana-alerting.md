# Grafana dashboards and alerting

TractusMind ships a provisioned local observability stack built from Prometheus, Alertmanager, and
Grafana. Dashboards and alert rules are repository-owned artifacts so changes are code-reviewed and
validated in CI rather than edited only through a browser.

## Local stack

`docker compose up --build` exposes:

```text
Grafana       http://localhost:3000
Prometheus    http://localhost:9090
Alertmanager  http://localhost:9093
```

Grafana credentials come from:

```bash
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change-this-before-production
```

Change the password before making Grafana reachable outside a trusted local network.

The Compose stack currently pins Prometheus `v3.13.2` and Alertmanager `v0.33.1`, and follows the
Grafana `13.1` minor tag so patch releases in that supported minor line can be picked up.

## Provisioned dashboards

Grafana loads dashboards from `config/grafana/dashboards/` into the `TractusMind` folder.

### API & RAG Overview

`overview.json` shows:

- request rate and 5xx ratio
- API p95 latency
- grounded-answer volume
- HTTP status rates and per-route p95 latency
- answer outcomes
- pipeline-stage p95 latency and errors
- retrieval-result count distribution

### Providers & Ingestion

`operations.json` shows:

- active Prometheus alerts
- provider request outcomes and retries
- circuit-breaker events
- provider retry delay p95
- worker jobs in progress and job outcomes
- ingestion outcomes and p95 duration by source
- incremental file changes
- source-lock contention
- Prometheus scrape health

### Quality Loop

`quality.json` shows event-level quality signals:

- positive/negative feedback submissions
- failed-answer and negative-feedback review signals
- successful admin review decision operations
- regression-promotion operations
- review root-cause classifications
- answer outcomes related to abstention

These Prometheus counters describe events. Exact current PostgreSQL state such as the number of
pending reviews remains available from `GET /v1/ops/quality/summary`; Grafana does not pretend an
event counter is a live backlog gauge.

## Alert rules

Prometheus loads `config/alerts/tractusmind.rules.yml` and sends firing alerts to Alertmanager.
Rules deliberately use sustained windows and minimum-volume guards where ratios could otherwise be
noisy.

Current alerts cover:

```text
critical  metrics target unavailable for 5m
critical  API 5xx ratio >5% for 10m with non-trivial traffic
critical  provider circuit opened
warning   API p95 >2s for 15m with non-trivial traffic
warning   provider transient failures >10% for 10m
warning   sustained provider retry pressure
warning   repeated RAG pipeline errors
warning   generation p95 >15s for 15m
warning   negative feedback >25% with at least 8 submissions
warning   failed-answer review-signal spike
warning   source ingestion failure
warning   worker job failure
warning   repeated source-lock contention
```

Thresholds are operational starting points, not benchmark-derived SLOs. Tune them only after
measured production traffic establishes normal request volume and latency distributions.

There is intentionally no fabricated queue-depth alert: `tractusmind_queue_enqueued_total` is an
enqueue counter, not backlog depth. Add a backlog rule only after a real queue-depth gauge is
implemented or a stable native Dramatiq metric is selected and validated.

Likewise, offline `unsafe_answer_rate` belongs to the production quality gate; it is not silently
reinterpreted as a live Prometheus metric.

## Alert delivery

The repository Alertmanager configuration groups and inhibits alerts, but its `default` receiver
contains no external integration. This is intentional: repository code does not contain Slack,
email, PagerDuty, webhook, or other notification credentials.

A deployment should add the required receiver using its secret-management system and keep the
routing policy under code review. Until a receiver integration is configured, alerts remain visible
in Prometheus, Alertmanager, and the Grafana Alertmanager datasource but are not sent externally.

## Production metrics authentication

The local Compose stack uses `APP_ENV=development`, where the API `/metrics` endpoint is open on the
private Compose network. In any other environment the API requires `METRICS_ADMIN_KEY` or
`OPS_ADMIN_KEY` through the `X-TractusMind-Metrics-Key` header.

For production Prometheus, inject the key from a mounted secret file rather than committing it:

```yaml
scrape_configs:
  - job_name: tractusmind-api
    metrics_path: /metrics
    http_headers:
      X-TractusMind-Metrics-Key:
        files:
          - /run/secrets/tractusmind_metrics_key
    static_configs:
      - targets: ["api:8000"]
```

Mount the secret only into Prometheus. Worker and scheduler metric ports should remain private to
the observability network.

## Quality-loop metric families

V18 adds bounded quality-loop metrics:

```text
tractusmind_quality_review_signals_total{trigger}
tractusmind_quality_review_decisions_total{action,root_cause}
tractusmind_quality_regression_promotions_total{benchmark_kind}
```

`trigger`, `action`, `root_cause`, and `benchmark_kind` come from finite application-controlled
enums. User text, reviewer notes, questions, interaction IDs, and other high-cardinality content are
never metric labels.

## CI validation

Normal CI validates the observability artifacts before tests:

```text
ruff check .
promtool check config config/prometheus.yml
amtool check-config config/alertmanager.yml
parse every Grafana dashboard JSON
validate docker compose configuration
```

`promtool check config` also parses the referenced rule files, so malformed PromQL or alert YAML
fails the build.
