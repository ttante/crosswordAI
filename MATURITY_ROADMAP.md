# CrosswordAI Maturity Roadmap

This roadmap converts the `Future production tasks` column in `IMPLEMENTATION_STATUS.md` into the next implementation backlog. The first production objective is to harden the core path end to end before broadening adapters, scale, and UI.

## Themes

### Production Adapters

- Postgres/pgvector live integration tests, full source-pack persistence, graph persistence, source-pack detail queries, and registry-backed metadata flows.
- S3/MinIO credentialed validation, artifact signing, backup/restore checks, retention policies, and artifact compaction.
- OpenTelemetry exporter, distributed trace propagation, persisted trace/artifact correlation, dashboard templates, and alert rules.
- Temporal/Prefect workflow adapter, resumable workflow checkpoints, retry/backoff, cancellation, recovery tests, and DB-backed batch queue.
- Ray executor, autoscaling worker pools, GPU telemetry, batch-size autotuning, and multi-node throughput benchmarks.

### Evaluation Depth

- Larger protected retrieval, taxonomy, candidate, clue, graph, route, and source-pack eval suites.
- CI regression gates, historical trend reports, taxonomy slice leaderboards, adversarial fuzzing, red-team fixtures, and judge calibration records.
- Prompt eval gates, clue-generation evals, model/prompt/route bakeoffs, statistical significance tests, and automated route recommendations.

### Model Quality

- Live Ollama/OpenAI-compatible integration tests, provider token/cost accounting, streaming, timeout cancellation, and model-call dashboards.
- Model-assisted taxonomy, candidate expansion, clue generation, ambiguity solving, crossword-aware wrong-answer search, and source-support judging.
- LangGraph runtime, role-specific tool sandboxes, persisted agent memory/events, disagreement analytics, self-play solver benchmarks, and production route guardrails.
- Distillation dataset validators, privacy filters, annotation review workflow, fine-tuning upload adapters, and human editor feedback labels.

### Security And Safety

- Managed secret-provider adapters, hosted RBAC integration, network egress controls, source-poisoning checks, export-time policy enforcement, policy registry integration, and compliance review.
- Backup automation, DR drill evidence, staged deployment manifests, rollback CLI, signed promotion approvals, audit-log persistence, and multi-environment rollout controls.

### Reporting And UX

- Dashboard UI, report signing, historical drift views, editor annotations, shareable demo bundles, editorial preview UI, internal source audit views, PDF/web/IPUZ/PUZ exports, and richer visual polish.
- Puzzle heatmaps, clue lineage, source coverage, model contribution, taxonomy drift, puzzle cards, model cards, quarantine postmortems, and promotion reports.

## Prioritized Backlog

| Rank | Workstream | Why It Comes First | Depends On |
| --- | --- | --- | --- |
| P0.1 | Hardened local core path | Proves the full product loop is traceable, testable, and publish-gated before live services are introduced. | Tickets 1-29 |
| P0.2 | Postgres metadata/source-pack adapter | Removes local-only metadata bottleneck and enables durable source, graph, model-call, batch, and eval records. | Hardened core path |
| P0.3 | Object storage validation and signing | Makes exported artifacts durable, immutable, auditable, and safe for hosted environments. | Hardened core path |
| P0.4 | OpenTelemetry exporter and dashboards | Provides production observability for latency, cost, QA gates, retrieval, and model routes. | Hardened core path |
| P0.5 | Managed secrets and environment controls | Blocks accidental insecure deployment and prepares staged rollout. | Production settings |
| P0.6 | Protected CI eval gate | Prevents regressions in publish gates, retrieval, clue QA, safety, and export policy. | Eval registry |
| P1.1 | Registry write workflow and promotion transactions | Enables controlled model/prompt/route changes with rollback. | Protected CI eval gate |
| P1.2 | Real batch queue and cancellation API | Makes batch generation reliable for large theme sets and bakeoffs. | Postgres adapter |
| P1.3 | Live model/provider integration | Introduces real model calls after governance, evals, and observability are in place. | Observability, secrets |
| P1.4 | Live connector integration with caching/rate limits | Broadens source quality while keeping network behavior governed. | Egress controls |
| P2.1 | Distributed Ray/GPU execution | Scales proven batch/eval workloads after local behavior is stable. | Real batch queue |
| P2.2 | Dashboard and editorial UI | Makes the inspection bundle useful to editors and demos after data contracts stabilize. | Reports/export contracts |

## Progress

| Rank | Status | Implemented Surface |
| --- | --- | --- |
| P0.1 | Complete | Hardened local core path with persisted artifacts, trace spans, publish gate, and protected eval gate. |
| P0.2 | Complete | Postgres metadata/source-pack adapter methods for source packs, documents, snippets, graph records, model calls, and health checks. |
| P0.3 | Complete | Artifact checksums, HMAC signing, signed export manifests, local object-store health, and injectable S3/MinIO validation. |
| P0.4 | Complete | OTLP-shaped trace payloads, exporter seam, trace/run/artifact/model-call correlation, dashboard metrics, and alert rules. |
| P0.5 | Complete | Managed secret-provider seam, deployment manifests, staged environment validation, egress checks, and readiness reports. |
| P0.6 | Next | Protected CI eval gate for publish, retrieval, clue QA, safety, and export policy regressions. |

## First Production Path

The first hardening slice is:

`source pack -> candidates -> grid -> clues -> QA -> exports -> observability -> protected eval gate`

Success criteria:

- Every run creates a durable run record and immutable artifacts.
- Every published puzzle has source IDs, QA gates, model lineage, public-safe exports, trace spans, and eval evidence.
- Hard-gate failures quarantine the puzzle and still produce inspectable artifacts.
- The full path runs locally without external credentials, then can be swapped to production adapters behind existing interfaces.
