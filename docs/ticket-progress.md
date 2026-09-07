# Ticket Progress Tracker

> Generated file. Do not manually edit generated sections. Use `foreman tickets` commands.

## Tracker Metadata
<!-- TRACKER_METADATA_START -->
| Field | Value |
|---|---|
| App | crosswordsAI |
| Queue Limit | 50 |
| Timezone | UTC |
| Generated At | 2026-06-08T01:30:48.368Z |
| Remaining Tickets | ≥50 |
<!-- TRACKER_METADATA_END -->

# Tracker Rules

## Purpose
This tracker is the operational build control surface for humans and builder agents.

## First file to read
Read `docs/ticket-progress.md` first. Do not scan the full backlog to choose work
unless the queue is empty or the user explicitly asks for broader planning.

## How to choose work
Choose the first row in `LLM_NEXT_QUEUE` where `Status` is `next` and `Blocked By` is `None`.

## Required queue maintenance rule
Every ticket update must regenerate `docs/ticket-progress.md`, including `LLM_NEXT_QUEUE`.
Use `foreman tickets update <id>` — never manually edit generated sections.

## Blocked work
Do not implement blocked rows unless the blocker itself is the approved next work.

## Done policy
Never mark a ticket `done` without required validation evidence or a documented test exception.
Use `foreman tickets complete <id> --validation-result passed --evidence "..."`.

## New work policy
Newly discovered work belongs in the Discovered Future Work Inbox.
Use `foreman tickets discover --summary "..." --rationale "..."`.

## Generated document policy
Do not manually edit generated sections of `docs/ticket-progress.md`.
Use the `foreman tickets` commands instead.

## STEP_STATUS protocol
When Foreman is running this project, include the ticket ID in your done marker:
  STEP_STATUS: done | ticket="T001" summary="implemented the feature"
Use `foreman tickets discover` for newly discovered work during a build run.

## LLM_NEXT_QUEUE
<!-- LLM_NEXT_QUEUE_START -->
| Rank | Ticket | Title | Status | Priority | Area | Depends On | Blocked By | Size | Risk | Next Action | Required Tests | Evidence | Likely Files |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CORE-001 | Python Project Foundation | next | P0 | platform | None | None | M | Low | Begin implementation | Unit test that a no-op CLI command emits a run ID and a structured JSON log line.; Test harness boots and discovers tests locally. | N/A until implemented. | src/crosswordai/__init__.py, src/crosswordai/cli.py, src/crosswordai/config.py, tests/ |
| 2 | CORE-002 | Postgres, Migrations, And Object Storage | blocked | P0 | platform | CORE-001 | CORE-001 | L | Medium | Resolve blockers: CORE-001 | Tests for immutable artifact write/read round-trip.; Tests for metadata persistence and retrieval through the storage abstraction. | N/A until implemented. | migrations/, src/crosswordai/storage.py, src/crosswordai/db.py |
| 3 | CORE-003 | Control Plane Registry Skeleton | blocked | P0 | platform | CORE-002 | CORE-002 | M | Low | Resolve blockers: CORE-002 | Tests that valid registry config loads and invalid entries fail validation.; CLI test for `registries inspect` output. | N/A until implemented. | config/registries/, src/crosswordai/registries.py |
| 4 | CORE-004 | Workflow Executor Interface | blocked | P0 | platform | CORE-001 | CORE-001 | M | Medium | Resolve blockers: CORE-001 | Test that a workflow resumes from a checkpointed completed stage.; Test that a failing stage records a structured failure reason. | N/A until implemented. | src/crosswordai/workflow.py |
| 5 | CORE-005 | Source-Pack Schema And User-Notes Ingestion | blocked | P0 | backend | CORE-002, CORE-003 | CORE-002, CORE-003 | L | Medium | Resolve blockers: CORE-002, CORE-003 | Test building a source pack from local notes.; Test that inspection exposes documents, snippets, trust, rights metadata, and artifact links. | N/A until implemented. | src/crosswordai/sources.py |
| 6 | CORE-006 | Rights And Safety Baseline | blocked | P0 | backend | CORE-005 | CORE-005 | L | High | Resolve blockers: CORE-005 | Red-team fixtures for lyrics, scripts, book excerpts, secrets, and prompt-injection content are blocked/quarantined.; Test that policy decisions attach to source-pack artifacts. | N/A until implemented. | src/crosswordai/safety.py |
| 7 | CORE-007 | Vector Store Foundation | blocked | P1 | backend | CORE-002, CORE-005 | CORE-002, CORE-005 | L | Medium | Resolve blockers: CORE-002, CORE-005 | Tests for vector, lexical, and metadata-filtered queries.; Test that hybrid retrieval returns cited evidence snippets. | N/A until implemented. | src/crosswordai/vectors.py |
| 8 | CORE-008 | Knowledge Graph Foundation | blocked | P1 | backend | CORE-005 | CORE-005 | M | Medium | Resolve blockers: CORE-005 | Test storing entities/relationships with aliases and canonical IDs.; Test that traversal proposes evidence-backed clue angles citing evidence IDs. | N/A until implemented. | src/crosswordai/graph.py |
| 9 | CORE-009 | Taxonomy Engine | blocked | P1 | backend | CORE-005 | CORE-005 | M | Medium | Resolve blockers: CORE-005 | Test taxonomy classification with confidence on golden examples.; Test that taxonomy selection changes entity schema, retrieval policy, and rights thresholds. | N/A until implemented. | src/crosswordai/taxonomy.py |
| 10 | CORE-010 | External Source Connectors | blocked | P1 | backend | CORE-005, CORE-009 | CORE-005, CORE-009 | L | Medium | Resolve blockers: CORE-005, CORE-009 | Test building a source pack from notes plus two external connectors.; Test that connectors snapshot metadata and preserve provenance/content hashes. | N/A until implemented. | src/crosswordai/sources.py, src/crosswordai/connectors/ |
| 11 | CORE-011 | Retrieval Evaluation Harness | blocked | P1 | ai-evals | CORE-007 | CORE-007 | M | Low | Resolve blockers: CORE-007 | Test computing recall@k, evidence precision, source diversity, stale-source on a fixed eval set.; Test that a regression below threshold fails the gate command. | N/A until implemented. | src/crosswordai/retrieval_eval.py, evals/retrieval/ |
| 12 | CORE-012 | Model Adapter And Routing Layer | blocked | P1 | ai | CORE-003 | CORE-003 | L | Medium | Resolve blockers: CORE-003 | Test that mock/local/cloud routes share one interface.; Test cache hit on identical normalized input and that budget limits halt calls. | N/A until implemented. | src/crosswordai/models.py, src/crosswordai/routing.py |
| 13 | CORE-013 | Prompt Templates And Structured Outputs | blocked | P1 | ai | CORE-012 | CORE-012 | M | Medium | Resolve blockers: CORE-012 | Test that prompt versions are recorded and diffable.; Test schema-constrained parsing plus repair of a malformed model output. | N/A until implemented. | src/crosswordai/prompts.py, src/crosswordai/models.py |
| 14 | CORE-014 | Answer Candidate Generation | blocked | P1 | backend | CORE-007, CORE-008, CORE-009 | CORE-007, CORE-008, CORE-009 | L | Medium | Resolve blockers: CORE-007, CORE-008, CORE-009 | Test that candidate pools are source-backed and adequately sized for a 15x15 theme.; Test deduplication by exact match, alias, root, and embedding similarity. | N/A until implemented. | src/crosswordai/candidates.py |
| 15 | CORE-015 | Deterministic Grid Solver | blocked | P1 | backend | CORE-014 | CORE-014 | XL | High | Resolve blockers: CORE-014 | Test that a legal grid generated from fixed theme entries is connected, symmetric, checked, and duplicate-free.; Test that invalid grids produce precise failure reasons. | N/A until implemented. | src/crosswordai/solver.py |
| 16 | CORE-016 | Clue Generation Pipeline | blocked | P1 | ai | CORE-007, CORE-012, CORE-013 | CORE-007, CORE-012, CORE-013 | L | Medium | Resolve blockers: CORE-007, CORE-012, CORE-013 | Test that each answer gets multiple clue candidates with evidence and model lineage.; Test schema validity of clue outputs across supported styles. | N/A until implemented. | src/crosswordai/clues.py |
| 17 | CORE-017 | Clue QA And Repair | blocked | P1 | ai | CORE-016, CORE-006 | CORE-016, CORE-006 | L | High | Resolve blockers: CORE-016, CORE-006 | Test that ambiguous/unsupported/leaking clues are repaired or quarantined.; Test that QA results attach to every clue candidate. | N/A until implemented. | src/crosswordai/qa.py |
| 18 | CORE-018 | Agentic Critic Workflows | blocked | P2 | ai | CORE-017, CORE-004 | CORE-017, CORE-004 | L | High | Resolve blockers: CORE-017, CORE-004 | Test that agents operate on typed artifacts and cannot override deterministic hard gates.; Test that agent disagreement is captured as eval data, and budgets bound loops. | N/A until implemented. | src/crosswordai/agents.py |
| 19 | CORE-019 | Publish Gate And Puzzle Exports | blocked | P1 | backend | CORE-015, CORE-017 | CORE-015, CORE-017 | L | High | Resolve blockers: CORE-015, CORE-017 | Test that any hard-gate failure quarantines and prevents publish with exact reasons.; Test that exports exclude hidden copyrighted source content. | N/A until implemented. | src/crosswordai/qa.py, src/crosswordai/exports.py |
| 20 | CORE-020 | OpenTelemetry And LLMOps Observability | blocked | P2 | observability | CORE-004, CORE-012 | CORE-004, CORE-012 | L | Medium | Resolve blockers: CORE-004, CORE-012 | Test that run inspection links puzzle back to source evidence and model calls.; Test that cost, latency, retry, cache-hit, and QA-gate metrics are present per run. | N/A until implemented. | src/crosswordai/observability.py |
| 21 | CORE-021 | Evaluation Registry And Golden Sets | blocked | P1 | ai-evals | CORE-011, CORE-019 | CORE-011, CORE-019 | L | Medium | Resolve blockers: CORE-011, CORE-019 | Test comparing two routes on frozen golden source packs.; Test that a protected hard-gate regression fails promotion. | N/A until implemented. | src/crosswordai/evals.py, evals/ |
| 22 | CORE-022 | Batch Generation Engine | blocked | P2 | backend | CORE-019, CORE-004 | CORE-019, CORE-004 | L | Medium | Resolve blockers: CORE-019, CORE-004 | Test generating puzzles for multiple themes in one batch run.; Test checkpoint resume, cancellation, budget stop, and reproducibility hashes. | N/A until implemented. | src/crosswordai/batch.py, src/crosswordai/experiments.py |
| 23 | CORE-023 | Model Bakeoff And Experimentation | blocked | P2 | ai-evals | CORE-021, CORE-022 | CORE-021, CORE-022 | L | Medium | Resolve blockers: CORE-021, CORE-022 | Test running an experiment matrix over multiple strategies on the same source packs.; Test that reports compare quality, cost, latency, publish rate, and failure modes. | N/A until implemented. | src/crosswordai/experiments.py |
| 24 | CORE-024 | Distributed Batch And GPU Throughput | blocked | P3 | platform | CORE-022 | CORE-022 | L | Medium | Resolve blockers: CORE-022 | Test that batch work distributes beyond a single process (Ray executor, mockable).; Test throughput/cost/failure metrics captured per worker and task type. | N/A until implemented. | src/crosswordai/distributed.py |
| 25 | CORE-025 | Advanced Model Routing | blocked | P2 | ai | CORE-012, CORE-023 | CORE-012, CORE-023 | L | Medium | Resolve blockers: CORE-012, CORE-023 | Test that advanced routes run in batch without replacing the baseline route.; Test shadow-mode report recommends promote/hold for a candidate route. | N/A until implemented. | src/crosswordai/routing.py |
| 26 | CORE-026 | Distillation Dataset Pipeline | blocked | P3 | ai | CORE-019, CORE-021 | CORE-019, CORE-021 | M | Medium | Resolve blockers: CORE-019, CORE-021 | Test building a frozen train/val/test split for one specialist task.; Test that dataset lineage references source packs and QA decisions. | N/A until implemented. | src/crosswordai/datasets.py |
| 27 | CORE-027 | Model Promotion And Rollback | blocked | P2 | ai | CORE-021, CORE-025 | CORE-021, CORE-025 | M | High | Resolve blockers: CORE-021, CORE-025 | Test that promotion is blocked without eval evidence.; Test that every promotion records a rollback target. | N/A until implemented. | src/crosswordai/promotion.py |
| 28 | CORE-028 | Enterprise Reports And Bells And Whistles | blocked | P3 | reports | CORE-019, CORE-020 | CORE-019, CORE-020 | L | Low | Resolve blockers: CORE-019, CORE-020 | Test that the inspection bundle includes heatmap, clue lineage, source coverage, model contribution, and cards.; Test quarantine postmortem content for a quarantined puzzle. | N/A until implemented. | src/crosswordai/reports.py |
| 29 | CORE-029 | Production Hardening | blocked | P2 | platform | CORE-002, CORE-003 | CORE-002, CORE-003 | L | High | Resolve blockers: CORE-002, CORE-003 | Test environment-separation config validation and egress allowlist enforcement.; Test secret-provider seam and readiness report generation. | N/A until implemented. | src/crosswordai/production.py, docs/operations.md |
| 30 | MAT-P0-1 | P0.1 Hardened local core path | blocked | P0 | platform | CORE-019, CORE-020, CORE-021 | CORE-019, CORE-020, CORE-021 | XL | High | Resolve blockers: CORE-019, CORE-020, CORE-021 | End-to-end test of the hardened core path producing durable run record + immutable artifacts.; Test that hard-gate failure quarantines yet still produces inspectable artifacts. | N/A until implemented. | src/crosswordai/core_path.py |
| 31 | MAT-P0-2 | P0.2 Postgres metadata/source-pack adapter | blocked | P0 | platform | MAT-P0-1 | MAT-P0-1 | L | High | Resolve blockers: MAT-P0-1 | Live Postgres/pgvector integration tests for source-pack, graph, model-call, batch, and eval persistence.; Adapter health-check tests. | N/A until implemented. | src/crosswordai/storage.py, src/crosswordai/db.py, migrations/ |
| 32 | MAT-P0-3 | P0.3 Object storage validation and signing | blocked | P0 | platform | MAT-P0-1 | MAT-P0-1 | M | Medium | Resolve blockers: MAT-P0-1 | Tests for artifact checksums, HMAC signing, and signed export manifest verification.; Injectable S3/MinIO validation tests and local object-store health test. | N/A until implemented. | src/crosswordai/storage.py, src/crosswordai/exports.py |
| 33 | MAT-P0-4 | P0.4 OpenTelemetry exporter and dashboards | blocked | P0 | observability | MAT-P0-1 | MAT-P0-1 | M | Medium | Resolve blockers: MAT-P0-1 | Test OTLP-shaped payload export and trace/run/artifact/model-call correlation.; Test dashboard metric payloads and alert-rule evaluation. | N/A until implemented. | src/crosswordai/observability.py |
| 34 | MAT-P0-5 | P0.5 Managed secrets and environment controls | blocked | P0 | security | MAT-P0-1 | MAT-P0-1 | M | High | Resolve blockers: MAT-P0-1 | Tests for secret-provider seam, environment validation, and egress allowlist checks.; Readiness report generation test. | N/A until implemented. | src/crosswordai/production.py, docs/operations.md |
| 35 | MAT-P0-6 | P0.6 Protected CI eval gate | blocked | P0 | ai-evals | CORE-021, MAT-P0-1 | CORE-021, MAT-P0-1 | M | High | Resolve blockers: CORE-021, MAT-P0-1 | CI test that a deliberate publish/retrieval/clue-QA/safety/export regression fails the gate.; Test that the gate runs against the frozen protected eval set. | N/A until implemented. | src/crosswordai/evals.py, .github/workflows/ |
| 36 | MAT-P1-1 | P1.1 Registry write workflow and promotion transactions | blocked | P1 | ai | MAT-P0-6, CORE-027 | MAT-P0-6, CORE-027 | L | High | Resolve blockers: MAT-P0-6, CORE-027 | Test transactional registry write with rollback on failure.; Test that promotion without eval evidence is rejected. | N/A until implemented. | src/crosswordai/promotion.py, src/crosswordai/registries.py |
| 37 | MAT-P1-2 | P1.2 Real batch queue and cancellation API | blocked | P1 | backend | MAT-P0-2, CORE-022 | MAT-P0-2, CORE-022 | L | Medium | Resolve blockers: MAT-P0-2, CORE-022 | Test DB-backed queue resume after interruption.; Test cancellation API stops a running batch and preserves checkpoints. | N/A until implemented. | src/crosswordai/batch.py |
| 38 | MAT-P1-3 | P1.3 Live model/provider integration | blocked | P1 | ai | MAT-P0-4, MAT-P0-5 | MAT-P0-4, MAT-P0-5 | L | High | Resolve blockers: MAT-P0-4, MAT-P0-5 | Live (and mocked) Ollama/OpenAI-compatible integration tests.; Tests for provider token/cost accounting, streaming, and timeout cancellation. | N/A until implemented. | src/crosswordai/models.py |
| 39 | MAT-P1-4 | P1.4 Live connector integration with caching/rate limits | blocked | P1 | backend | MAT-P0-5, CORE-010 | MAT-P0-5, CORE-010 | L | Medium | Resolve blockers: MAT-P0-5, CORE-010 | Live-network integration tests for connectors (mockable in CI).; Tests for connector caching, rate-limit/backoff, and source refresh. | N/A until implemented. | src/crosswordai/connectors/, src/crosswordai/sources.py |
| 40 | MAT-P2-1 | P2.1 Distributed Ray/GPU execution | blocked | P2 | platform | MAT-P1-2, CORE-024 | MAT-P1-2, CORE-024 | L | Medium | Resolve blockers: MAT-P1-2, CORE-024 | Multi-worker Ray execution test (mockable) for batch/eval sweeps.; Tests for GPU telemetry capture and batch-size autotuning decisions. | N/A until implemented. | src/crosswordai/distributed.py |
| 41 | MAT-P2-2 | P2.2 Dashboard and editorial UI | blocked | P2 | frontend | MAT-P0-1 | MAT-P0-1 | XL | Medium | Resolve blockers: MAT-P0-1 | UI tests for dashboard and editorial review surfaces against stable contracts. | N/A until implemented. | web/, src/crosswordai/web_api.py |
| 42 | WEB-001 | FastAPI service skeleton | blocked | P1 | frontend | MAT-P0-1 | MAT-P0-1 | M | Low | Resolve blockers: MAT-P0-1 | FastAPI TestClient tests for health, error shape, and correlation ID. | N/A until implemented. | src/crosswordai/web_api.py |
| 43 | WEB-002 | Shared contracts and fixtures | blocked | P1 | frontend | WEB-001 | WEB-001 | M | Medium | Resolve blockers: WEB-001 | Contract tests and fixture validation. | N/A until implemented. | src/crosswordai/web_api.py, web/src/fixtures/ |
| 44 | WEB-003 | Scaffold React app | next | P1 | frontend | None | None | M | Low | Begin implementation | Smoke unit test for app shell. | N/A until implemented. | web/ |
| 45 | WEB-004 | Typed API client | blocked | P1 | frontend | WEB-002, WEB-003 | WEB-002, WEB-003 | M | Medium | Resolve blockers: WEB-002, WEB-003 | API client unit tests with success, failure, timeout, and malformed payload cases. | N/A until implemented. | web/src/api/ |
| 46 | WEB-005 | Design tokens | blocked | P1 | frontend | WEB-003 | WEB-003 | S | Low | Resolve blockers: WEB-003 | Token import test and visual smoke test. | N/A until implemented. | web/src/styles/tokens.ts |
| 47 | WEB-006 | App shell and routing | blocked | P1 | frontend | WEB-004, WEB-005 | WEB-004, WEB-005 | M | Low | Resolve blockers: WEB-004, WEB-005 | Router tests and Playwright route smoke tests. | N/A until implemented. | web/src/app/, web/src/routes/ |
| 48 | WEB-007 | Generation API slice | blocked | P1 | frontend | WEB-001, WEB-002 | WEB-001, WEB-002 | L | Medium | Resolve blockers: WEB-001, WEB-002 | FastAPI route tests using generated or fixture-backed artifacts. | N/A until implemented. | src/crosswordai/web_api.py |
| 49 | WEB-008 | New puzzle workflow | blocked | P1 | frontend | WEB-006, WEB-007 | WEB-006, WEB-007 | M | Low | Resolve blockers: WEB-006, WEB-007 | Form validation tests and API submit test. | N/A until implemented. | web/src/features/create/ |
| 50 | WEB-009 | Studio dashboard | blocked | P1 | frontend | WEB-006, WEB-007 | WEB-006, WEB-007 | M | Low | Resolve blockers: WEB-006, WEB-007 | Component tests for empty, loading, populated, and error states. | N/A until implemented. | web/src/features/dashboard/ |
<!-- LLM_NEXT_QUEUE_END -->

## Active Ticket Status
<!-- ACTIVE_TICKET_STATUS_START -->
| Ticket | Title | Status | Priority | Area | Owner | last_worked_at | completed_at | Depends On | Blockers | Next Action | Acceptance / Test Gate | Evidence | Future Work / Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CORE-001 | Python Project Foundation | next | P0 | platform | unassigned | N/A | N/A | None | None | Begin implementation | `crosswordai --help` works.; A no-op command creates a run ID and structured log.; Unit tests run locally. | N/A until implemented. | N/A |
| CORE-002 | Postgres, Migrations, And Object Storage | blocked | P0 | platform | unassigned | N/A | N/A | CORE-001 | CORE-001 | Resolve blockers: CORE-001 | A run can store and retrieve structured metadata plus an object artifact.; Storage helpers are covered by tests. | N/A until implemented. | N/A |
| CORE-003 | Control Plane Registry Skeleton | blocked | P0 | platform | unassigned | N/A | N/A | CORE-002 | CORE-002 | Resolve blockers: CORE-002 | Registries load from versioned config.; Invalid registry entries fail validation.; CLI can inspect active registry versions. | N/A until implemented. | N/A |
| CORE-004 | Workflow Executor Interface | blocked | P0 | platform | unassigned | N/A | N/A | CORE-001 | CORE-001 | Resolve blockers: CORE-001 | A toy multi-stage workflow can resume from a completed stage.; Failed stages preserve structured failure reasons. | N/A until implemented. | N/A |
| CORE-005 | Source-Pack Schema And User-Notes Ingestion | blocked | P0 | backend | unassigned | N/A | N/A | CORE-002, CORE-003 | CORE-002, CORE-003 | Resolve blockers: CORE-002, CORE-003 | A source pack can be built from local notes.; Source pack inspection shows documents, snippets, trust, rights metadata, and artifact links. | N/A until implemented. | N/A |
| CORE-006 | Rights And Safety Baseline | blocked | P0 | backend | unassigned | N/A | N/A | CORE-005 | CORE-005 | Resolve blockers: CORE-005 | Long lyrics, scripts, modern-book excerpts, secrets, and prompt-injection attempts are blocked or quarantined.; Policy decisions are logged and attached to source-pack artifacts. | N/A until implemented. | N/A |
| CORE-007 | Vector Store Foundation | blocked | P1 | backend | unassigned | N/A | N/A | CORE-002, CORE-005 | CORE-002, CORE-005 | Resolve blockers: CORE-002, CORE-005 | Source chunks can be embedded and queried.; Hybrid retrieval returns cited evidence snippets.; Retrieval tests cover vector, lexical, and metadata-filtered queries. | N/A until implemented. | N/A |
| CORE-008 | Knowledge Graph Foundation | blocked | P1 | backend | unassigned | N/A | N/A | CORE-005 | CORE-005 | Resolve blockers: CORE-005 | A source pack can store entities and relationships.; Graph traversal can propose evidence-backed clue angles. | N/A until implemented. | N/A |
| CORE-009 | Taxonomy Engine | blocked | P1 | backend | unassigned | N/A | N/A | CORE-005 | CORE-005 | Resolve blockers: CORE-005 | Source packs are assigned taxonomy with confidence.; Taxonomy drives entity schema, retrieval policy, and rights thresholds. | N/A until implemented. | N/A |
| CORE-010 | External Source Connectors | blocked | P1 | backend | unassigned | N/A | N/A | CORE-005, CORE-009 | CORE-005, CORE-009 | Resolve blockers: CORE-005, CORE-009 | Source packs can be built from user notes plus at least two external source types.; Connectors snapshot source metadata and preserve provenance. | N/A until implemented. | N/A |
| CORE-011 | Retrieval Evaluation Harness | blocked | P1 | ai-evals | unassigned | N/A | N/A | CORE-007 | CORE-007 | Resolve blockers: CORE-007 | Retrieval strategies can be compared on a fixed source-pack eval set.; Retrieval regressions can fail CI or local gate commands. | N/A until implemented. | N/A |
| CORE-012 | Model Adapter And Routing Layer | blocked | P1 | ai | unassigned | N/A | N/A | CORE-003 | CORE-003 | Resolve blockers: CORE-003 | Mock, local, and cloud-capable model routes share the same interface.; Model calls are cached and logged.; Budget limits stop runaway jobs. | N/A until implemented. | N/A |
| CORE-013 | Prompt Templates And Structured Outputs | blocked | P1 | ai | unassigned | N/A | N/A | CORE-012 | CORE-012 | Resolve blockers: CORE-012 | Prompt changes are versioned.; Model output parsing failures are captured and repairable. | N/A until implemented. | N/A |
| CORE-014 | Answer Candidate Generation | blocked | P1 | backend | unassigned | N/A | N/A | CORE-007, CORE-008, CORE-009 | CORE-007, CORE-008, CORE-009 | Resolve blockers: CORE-007, CORE-008, CORE-009 | Candidate pools are source-backed and large enough for common 15x15 themes.; Duplicate and weak candidates are filtered before grid solving. | N/A until implemented. | N/A |
| CORE-015 | Deterministic Grid Solver | blocked | P1 | backend | unassigned | N/A | N/A | CORE-014 | CORE-014 | Resolve blockers: CORE-014 | Legal grids can be generated from fixed theme entries.; Invalid grids produce precise failure reasons. | N/A until implemented. | N/A |
| CORE-016 | Clue Generation Pipeline | blocked | P1 | ai | unassigned | N/A | N/A | CORE-007, CORE-012, CORE-013 | CORE-007, CORE-012, CORE-013 | Resolve blockers: CORE-007, CORE-012, CORE-013 | Each answer receives multiple clue candidates with evidence and model lineage.; Clue outputs are schema-valid. | N/A until implemented. | N/A |
| CORE-017 | Clue QA And Repair | blocked | P1 | ai | unassigned | N/A | N/A | CORE-016, CORE-006 | CORE-016, CORE-006 | Resolve blockers: CORE-016, CORE-006 | Weak clues are repaired or quarantined.; QA results attach to every clue candidate. | N/A until implemented. | N/A |
| CORE-018 | Agentic Critic Workflows | blocked | P2 | ai | unassigned | N/A | N/A | CORE-017, CORE-004 | CORE-017, CORE-004 | Resolve blockers: CORE-017, CORE-004 | Agent workflows operate on typed artifacts.; Agents cannot override deterministic hard gates.; Agent disagreement is recorded as eval data. | N/A until implemented. | N/A |
| CORE-019 | Publish Gate And Puzzle Exports | blocked | P1 | backend | unassigned | N/A | N/A | CORE-015, CORE-017 | CORE-015, CORE-017 | Resolve blockers: CORE-015, CORE-017 | No puzzle publishes with hard-gate failures.; Exported artifacts exclude hidden copyrighted source content. | N/A until implemented. | N/A |
| CORE-020 | OpenTelemetry And LLMOps Observability | blocked | P2 | observability | unassigned | N/A | N/A | CORE-004, CORE-012 | CORE-004, CORE-012 | Resolve blockers: CORE-004, CORE-012 | A run can be inspected from puzzle back to source evidence and model calls.; Cost, latency, retry count, cache hit rate, and QA gates are visible per run. | N/A until implemented. | N/A |
| CORE-021 | Evaluation Registry And Golden Sets | blocked | P1 | ai-evals | unassigned | N/A | N/A | CORE-011, CORE-019 | CORE-011, CORE-019 | Resolve blockers: CORE-011, CORE-019 | Evals can compare two routes.; Protected hard-gate regressions fail promotion. | N/A until implemented. | N/A |
| CORE-022 | Batch Generation Engine | blocked | P2 | backend | unassigned | N/A | N/A | CORE-019, CORE-004 | CORE-019, CORE-004 | Resolve blockers: CORE-019, CORE-004 | The system can generate puzzles for many themes in one run.; Batch results are inspectable and reproducible. | N/A until implemented. | N/A |
| CORE-023 | Model Bakeoff And Experimentation | blocked | P2 | ai-evals | unassigned | N/A | N/A | CORE-021, CORE-022 | CORE-021, CORE-022 | Resolve blockers: CORE-021, CORE-022 | Multiple model-responsibility strategies can be tested on the same source packs.; Reports compare quality, cost, latency, publish rate, and failure modes. | N/A until implemented. | N/A |
| CORE-024 | Distributed Batch And GPU Throughput | blocked | P3 | platform | unassigned | N/A | N/A | CORE-022 | CORE-022 | Resolve blockers: CORE-022 | Batch evals can scale beyond a single local process.; Throughput, cost, and failure metrics are captured by worker and task type. | N/A until implemented. | N/A |
| CORE-025 | Advanced Model Routing | blocked | P2 | ai | unassigned | N/A | N/A | CORE-012, CORE-023 | CORE-012, CORE-023 | Resolve blockers: CORE-012, CORE-023 | Advanced routes can run in batch without replacing baseline production routes.; Shadow-mode reports show whether candidate routes should be promoted. | N/A until implemented. | N/A |
| CORE-026 | Distillation Dataset Pipeline | blocked | P3 | ai | unassigned | N/A | N/A | CORE-019, CORE-021 | CORE-019, CORE-021 | Resolve blockers: CORE-019, CORE-021 | At least one specialist task has a frozen dataset ready for fine-tuning or classifier training.; Dataset lineage points back to source packs and QA decisions. | N/A until implemented. | N/A |
| CORE-027 | Model Promotion And Rollback | blocked | P2 | ai | unassigned | N/A | N/A | CORE-021, CORE-025 | CORE-021, CORE-025 | Resolve blockers: CORE-021, CORE-025 | No route can be promoted without eval evidence.; Rollback target is always recorded. | N/A until implemented. | N/A |
| CORE-028 | Enterprise Reports And Bells And Whistles | blocked | P3 | reports | unassigned | N/A | N/A | CORE-019, CORE-020 | CORE-019, CORE-020 | Resolve blockers: CORE-019, CORE-020 | A generated puzzle has a polished inspection bundle suitable for demos, debugging, and future UI surfaces. | N/A until implemented. | N/A |
| CORE-029 | Production Hardening | blocked | P2 | platform | unassigned | N/A | N/A | CORE-002, CORE-003 | CORE-002, CORE-003 | Resolve blockers: CORE-002, CORE-003 | The platform has a credible path from local CLI to staged production deployment. | N/A until implemented. | N/A |
| MAT-P0-1 | P0.1 Hardened local core path | blocked | P0 | platform | unassigned | N/A | N/A | CORE-019, CORE-020, CORE-021 | CORE-019, CORE-020, CORE-021 | Resolve blockers: CORE-019, CORE-020, CORE-021 | Every run creates a durable run record and immutable artifacts.; Every published puzzle has source IDs, QA gates, model lineage, public-safe exports, trace spans, and eval evidence.; Hard-gate failures quarantine the puzzle and still produce inspectable artifacts.; The full path runs locally without external credentials, then can swap to production adapters behind existing interfaces. | N/A until implemented. | N/A |
| MAT-P0-2 | P0.2 Postgres metadata/source-pack adapter | blocked | P0 | platform | unassigned | N/A | N/A | MAT-P0-1 | MAT-P0-1 | Resolve blockers: MAT-P0-1 | Source packs, documents, snippets, graph records, and model calls persist to Postgres via the adapter.; Adapter exposes health checks and is validated against live Postgres/pgvector. | N/A until implemented. | N/A |
| MAT-P0-3 | P0.3 Object storage validation and signing | blocked | P0 | platform | unassigned | N/A | N/A | MAT-P0-1 | MAT-P0-1 | Resolve blockers: MAT-P0-1 | Artifacts carry checksums and HMAC signatures; export manifests are signed.; S3/MinIO adapter is validated with credentials and object-store health checks pass. | N/A until implemented. | N/A |
| MAT-P0-4 | P0.4 OpenTelemetry exporter and dashboards | blocked | P0 | observability | unassigned | N/A | N/A | MAT-P0-1 | MAT-P0-1 | Resolve blockers: MAT-P0-1 | OTLP-shaped trace payloads export through an exporter seam.; Trace/run/artifact/model-call correlation, dashboard metrics, and alert rules are available. | N/A until implemented. | N/A |
| MAT-P0-5 | P0.5 Managed secrets and environment controls | blocked | P0 | security | unassigned | N/A | N/A | MAT-P0-1 | MAT-P0-1 | Resolve blockers: MAT-P0-1 | Managed secret-provider seam and deployment manifests exist.; Staged environment validation, egress checks, and readiness reports pass. | N/A until implemented. | N/A |
| MAT-P0-6 | P0.6 Protected CI eval gate | blocked | P0 | ai-evals | unassigned | N/A | N/A | CORE-021, MAT-P0-1 | CORE-021, MAT-P0-1 | Resolve blockers: CORE-021, MAT-P0-1 | CI eval gate blocks merges that regress publish, retrieval, clue QA, safety, or export-policy gates.; Gate runs on a frozen protected eval set and fails on protected hard-gate regressions. | N/A until implemented. | N/A |
| MAT-P1-1 | P1.1 Registry write workflow and promotion transactions | blocked | P1 | ai | unassigned | N/A | N/A | MAT-P0-6, CORE-027 | MAT-P0-6, CORE-027 | Resolve blockers: MAT-P0-6, CORE-027 | Registry mutations occur only through transactional promotion with eval evidence.; Every promotion records a rollback target and audit record. | N/A until implemented. | N/A |
| MAT-P1-2 | P1.2 Real batch queue and cancellation API | blocked | P1 | backend | unassigned | N/A | N/A | MAT-P0-2, CORE-022 | MAT-P0-2, CORE-022 | Resolve blockers: MAT-P0-2, CORE-022 | Batch runs are resumable from a DB-backed queue.; A cancellation API stops in-flight batches and records partial results. | N/A until implemented. | N/A |
| MAT-P1-3 | P1.3 Live model/provider integration | blocked | P1 | ai | unassigned | N/A | N/A | MAT-P0-4, MAT-P0-5 | MAT-P0-4, MAT-P0-5 | Resolve blockers: MAT-P0-4, MAT-P0-5 | Live Ollama and OpenAI-compatible routes pass integration tests behind existing adapter interfaces.; Provider-specific token/cost accounting, streaming, and timeout cancellation work. | N/A until implemented. | N/A |
| MAT-P1-4 | P1.4 Live connector integration with caching/rate limits | blocked | P1 | backend | unassigned | N/A | N/A | MAT-P0-5, CORE-010 | MAT-P0-5, CORE-010 | Resolve blockers: MAT-P0-5, CORE-010 | Live connectors run within network allowlists with caching and rate-limit/backoff.; Source refresh workflows update snapshots while preserving provenance. | N/A until implemented. | N/A |
| MAT-P2-1 | P2.1 Distributed Ray/GPU execution | blocked | P2 | platform | unassigned | N/A | N/A | MAT-P1-2, CORE-024 | MAT-P1-2, CORE-024 | Resolve blockers: MAT-P1-2, CORE-024 | Real Ray executor runs batch/eval sweeps across multiple workers/nodes.; GPU utilization telemetry and batch-size autotuning are captured with throughput benchmarks. | N/A until implemented. | N/A |
| MAT-P2-2 | P2.2 Dashboard and editorial UI | blocked | P2 | frontend | unassigned | N/A | N/A | MAT-P0-1 | MAT-P0-1 | Resolve blockers: MAT-P0-1 | Editors can inspect runs, reports, and the inspection bundle through a UI after contracts stabilize.; UI consumes stable report/export contracts without bypassing publish gates. | N/A until implemented. | N/A |
| WEB-001 | FastAPI service skeleton | blocked | P1 | frontend | unassigned | N/A | N/A | MAT-P0-1 | MAT-P0-1 | Resolve blockers: MAT-P0-1 | `uvicorn crosswordai.web_api:app` starts locally and `GET /health` returns typed JSON. | N/A until implemented. | N/A |
| WEB-002 | Shared contracts and fixtures | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-001 | WEB-001 | Resolve blockers: WEB-001 | Frontend and backend agree on the initial JSON shapes before UI code depends on them. | N/A until implemented. | N/A |
| WEB-003 | Scaffold React app | next | P1 | frontend | unassigned | N/A | N/A | None | None | Begin implementation | `npm install`, `npm run test`, and `npm run build` work from `web/`. | N/A until implemented. | N/A |
| WEB-004 | Typed API client | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-002, WEB-003 | WEB-002, WEB-003 | Resolve blockers: WEB-002, WEB-003 | Components do not call fetch directly.; Errors display consistent user-facing states. | N/A until implemented. | N/A |
| WEB-005 | Design tokens | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-003 | WEB-003 | Resolve blockers: WEB-003 | Theme tokens are centralized and documented in code.; No hard-coded repeated colors in components. | N/A until implemented. | N/A |
| WEB-006 | App shell and routing | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-004, WEB-005 | WEB-004, WEB-005 | Resolve blockers: WEB-004, WEB-005 | Each route renders a stable layout with accessible page title and navigation state. | N/A until implemented. | N/A |
| WEB-007 | Generation API slice | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-001, WEB-002 | WEB-001, WEB-002 | Resolve blockers: WEB-001, WEB-002 | A UI can create a local generation request and read back run state without CLI usage. | N/A until implemented. | N/A |
| WEB-008 | New puzzle workflow | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-006, WEB-007 | WEB-006, WEB-007 | Resolve blockers: WEB-006, WEB-007 | Form validates required inputs and starts a source-pack or generation request. | N/A until implemented. | N/A |
| WEB-009 | Studio dashboard | blocked | P1 | frontend | unassigned | N/A | N/A | WEB-006, WEB-007 | WEB-006, WEB-007 | Resolve blockers: WEB-006, WEB-007 | Creator can see what needs attention within one screen. | N/A until implemented. | N/A |
<!-- ACTIVE_TICKET_STATUS_END -->

## Blocked Tickets
<!-- BLOCKED_TICKETS_START -->
| Ticket | Blocked By | Blocker Type | Owner | First Blocked At | Last Checked At | Needed Decision / Action | Unblock Criteria | Notes |
|---|---|---|---|---|---|---|---|---|
| CORE-002 | CORE-001 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-003 | CORE-002 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-004 | CORE-001 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-005 | CORE-002, CORE-003 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-006 | CORE-005 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-007 | CORE-002, CORE-005 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-008 | CORE-005 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-009 | CORE-005 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-010 | CORE-005, CORE-009 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-011 | CORE-007 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-012 | CORE-003 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-013 | CORE-012 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-014 | CORE-007, CORE-008, CORE-009 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-015 | CORE-014 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-016 | CORE-007, CORE-012, CORE-013 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-017 | CORE-016, CORE-006 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-018 | CORE-017, CORE-004 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-019 | CORE-015, CORE-017 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-020 | CORE-004, CORE-012 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-021 | CORE-011, CORE-019 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-022 | CORE-019, CORE-004 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-023 | CORE-021, CORE-022 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-024 | CORE-022 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-025 | CORE-012, CORE-023 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-026 | CORE-019, CORE-021 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-027 | CORE-021, CORE-025 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-028 | CORE-019, CORE-020 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| CORE-029 | CORE-002, CORE-003 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P0-1 | CORE-019, CORE-020, CORE-021 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P0-2 | MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P0-3 | MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P0-4 | MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P0-5 | MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P0-6 | CORE-021, MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P1-1 | MAT-P0-6, CORE-027 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P1-2 | MAT-P0-2, CORE-022 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P1-3 | MAT-P0-4, MAT-P0-5 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P1-4 | MAT-P0-5, CORE-010 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P2-1 | MAT-P1-2, CORE-024 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| MAT-P2-2 | MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-001 | MAT-P0-1 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-002 | WEB-001 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-004 | WEB-002, WEB-003 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-005 | WEB-003 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-006 | WEB-004, WEB-005 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-007 | WEB-001, WEB-002 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-008 | WEB-006, WEB-007 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
| WEB-009 | WEB-006, WEB-007 | dependency | unassigned | N/A | N/A | Resolve blockers | N/A | N/A |
<!-- BLOCKED_TICKETS_END -->

## Recently Completed Context
<!-- RECENTLY_COMPLETED_CONTEXT_START -->
_No recently completed tickets pinned for context._
<!-- RECENTLY_COMPLETED_CONTEXT_END -->

## Discovered Future Work Inbox
<!-- DISCOVERED_FUTURE_WORK_START -->
_No discovered future work items._
<!-- DISCOVERED_FUTURE_WORK_END -->

## Archive Index
<!-- ARCHIVE_INDEX_START -->
_No archived tickets yet._
<!-- ARCHIVE_INDEX_END -->

## Last Validation Snapshot
| Timestamp | Scope | Result | Commands | Evidence | Notes |
|---|---|---|---|---|---|
| N/A | tracker | not_run | N/A | N/A | No validation snapshots recorded yet. |

## Work Log
<!-- WORK_LOG_START -->
_No work log entries yet._
<!-- WORK_LOG_END -->

## Four-Pass Validation Checklist

Run `foreman tickets validate` to execute all passes.

1. **Schema & source** — config.yaml, tickets.yaml schema, unique IDs/orders, valid deps, no cycles.
2. **State** — SQLite migrations applied, all state ticket_ids exist in tickets.yaml, done tickets have evidence.
3. **Queue** — correct length, contiguous ranks, no done/canceled, sorted by order, blocked rows marked.
4. **Generated doc** — required sections and marker comments present, every queued ticket in Active Status.
