# Themed Crossword Puzzle Generator Plan

## 1. Product Target

Build a production-grade CLI pipeline that generates American-style themed crossword puzzles from curated source material. The first version is not a web app. It is the generation engine, data pipeline, model-governance layer, and automated QA system that a future app can depend on.

The system should produce publishable puzzles automatically when quality gates pass, and quarantine failed puzzles with exact reasons when they do not.

Core goals:

- Generate themed American-style crossword puzzles from a free-text topic, document, article, Wikipedia page, lesson, or custom notes.
- Use deterministic crossword construction for grid legality and fill correctness.
- Use AI for theme research, taxonomy, clue ideation, clue writing, ambiguity checks, source-backed validation, difficulty tuning, and quality review.
- Keep AI use efficient through model routing, caching, staged validation, eval-driven improvement, and later distillation.
- Maintain strong provenance for all factual clue material.
- Prevent unsafe or legally risky use of copyrighted lyrics, scripts, quotes, and long excerpts.
- Produce auditable artifacts: puzzle, answer key, source map, QA scorecard, model-call trace, and publish decision.

Non-goals for v1:

- No hosted SaaS product.
- No end-user web UI.
- No billing, auth, collaboration, or sharing features.
- No fully manual puzzle editor.
- No immediate fine-tuning before enough eval data exists.

## 2. Success Criteria

A generated puzzle is publishable only if all hard gates pass.

Publishable means:

- The grid is legal, connected, symmetric, and fully checked according to the selected American-style crossword rules.
- The theme entries are cohesive, source-backed, correctly placed, and interesting.
- The fill is clean, valid, non-duplicative, and appropriate for the configured difficulty.
- Every factual clue can be traced to source evidence or marked as definition/common-language based.
- Clues uniquely resolve to their answers within expected crossword conventions.
- Difficulty labels are calibrated across the puzzle.
- No disallowed copyrighted text is stored or emitted.
- Offensive, misleading, hallucinated, or low-quality clues are blocked.
- The system can explain why the puzzle passed, failed, or was quarantined.

Operational targets:

- Every run is reproducible from source-pack version, wordlist version, solver config, model registry version, prompt versions, and seed.
- Every model call is logged with enough metadata to evaluate quality, cost, latency, and downstream impact.
- Expensive model calls are reserved for high-value tasks, uncertain decisions, or final review.
- Failed and repaired outputs become labeled data for evals and future distillation.

## 3. System Architecture

The system is a staged pipeline. Each stage emits structured artifacts and validation results. Later stages consume only validated artifacts unless a retry or repair path explicitly requests weaker candidates.

Pipeline stages:

1. Source-pack creation
2. Taxonomy and theme modeling
3. Answer candidate generation
4. Candidate scoring and filtering
5. Grid construction
6. Clue generation
7. Multi-pass validation and repair
8. Final QA and publish decision
9. Artifact export and run reporting

Primary implementation stack:

- Python for the CLI, pipeline orchestration, NLP tooling, retrieval, constraint solving, evals, and model integrations.
- Postgres for structured state, provenance, run metadata, QA results, model-call logs, and publish decisions.
- Object storage for source snapshots, generated puzzle artifacts, exports, run bundles, and eval datasets.
- A deterministic crossword solver/search engine for grid construction.
- Local embedding models for retrieval, deduplication, semantic checks, and theme consistency.
- Hybrid local/cloud LLM routing for generation and validation.

Suggested Python package boundaries:

- `crosswordai.cli`: command-line entrypoints.
- `crosswordai.sources`: source ingestion, snapshots, provenance, and rights metadata.
- `crosswordai.taxonomy`: subject classification and taxonomy-specific enrichment.
- `crosswordai.candidates`: answer and clue-angle generation.
- `crosswordai.solver`: grid construction and fill validation.
- `crosswordai.clues`: clue generation, style rewriting, and difficulty tuning.
- `crosswordai.qa`: validation gates, scoring, repair logic, and publish decisions.
- `crosswordai.models`: model registry, routing, caching, prompt templates, and call logging.
- `crosswordai.evals`: offline test sets, regression evals, model comparisons, and distillation datasets.
- `crosswordai.exports`: JSON, PDF-ready data, image-ready data, and web-play payloads.

## 4. CLI Design

Initial commands:

```bash
crosswordai source-pack build --theme "Miles Davis" --sources wikipedia wikidata musicbrainz official user-notes.md
crosswordai source-pack inspect --id <source_pack_id>
crosswordai generate --source-pack <source_pack_id> --size 15x15 --difficulty standard --style trivia
crosswordai evaluate --puzzle <puzzle_id>
crosswordai publish --puzzle <puzzle_id>
crosswordai runs inspect <run_id>
crosswordai exports create --puzzle <puzzle_id> --format json
```

Important CLI behavior:

- Commands must be idempotent when given the same source-pack version, config, and seed.
- Every command emits a run ID.
- Every command writes structured logs.
- Every failed command should produce a machine-readable failure reason.
- The `publish` command never overrides failed hard gates.

## 5. Core Data Model

### SourcePack

A versioned bundle of theme knowledge.

Fields:

- `id`
- `theme`
- `normalized_theme`
- `taxonomy`
- `source_documents`
- `source_snapshots`
- `entities`
- `relationships`
- `evidence_snippets`
- `rights_metadata`
- `quality_score`
- `created_at`
- `version`

### SourceDocument

A source used during generation.

Fields:

- `id`
- `source_pack_id`
- `source_type`
- `url_or_path`
- `title`
- `author_or_provider`
- `retrieved_at`
- `license_or_rights_status`
- `trust_score`
- `content_hash`
- `object_storage_uri`

### EvidenceSnippet

A short, auditable piece of supporting evidence.

Fields:

- `id`
- `source_document_id`
- `snippet_text`
- `start_locator`
- `end_locator`
- `snippet_hash`
- `rights_risk`
- `allowed_use`
- `derived_entities`

Do not store full copyrighted lyrics, scripts, poems, or long passages in this table.

### AnswerCandidate

A possible crossword answer.

Fields:

- `id`
- `source_pack_id`
- `answer_text`
- `normalized_answer`
- `enumeration`
- `theme_role`
- `taxonomy_tags`
- `difficulty_estimate`
- `familiarity_score`
- `crosswordese_risk`
- `source_support`
- `novelty_score`
- `duplicate_group`
- `rights_risk`
- `status`

### ClueCandidate

A possible clue for an answer.

Fields:

- `id`
- `answer_candidate_id`
- `clue_text`
- `clue_style`
- `difficulty`
- `source_evidence`
- `ambiguity_score`
- `fact_confidence`
- `rights_risk`
- `model_lineage`
- `qa_status`

### PuzzleDraft

A generated puzzle before publish.

Fields:

- `id`
- `source_pack_id`
- `puzzle_spec`
- `grid`
- `answers`
- `clues`
- `crossings`
- `theme_entries`
- `solver_config`
- `model_lineage`
- `qa_scorecard`
- `publish_status`

### ModelCall

Trace of any model request.

Fields:

- `id`
- `run_id`
- `task_type`
- `model_id`
- `model_provider`
- `prompt_template_version`
- `input_hash`
- `output_hash`
- `parameters`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `estimated_cost`
- `cache_hit`
- `retry_count`
- `validation_result`
- `downstream_artifact_id`

## 6. Source Packs And Knowledge Strategy

The system should not rely on one LLM prompt to know the theme. It should build a source pack first, then generate from that grounded context.

Supported source types:

- User notes.
- Wikipedia pages.
- Wikidata-style structured facts.
- Official websites.
- MusicBrainz-like artist and release metadata.
- TMDB/IMDb-like film and TV metadata where API terms allow it.
- OpenLibrary or public-domain text metadata for books.
- Curated article snippets.
- Classroom or lesson documents.

Source ranking:

- Highest trust: user-provided notes, official sources, structured databases with stable IDs.
- Medium trust: Wikipedia, reputable encyclopedic or journalistic sources.
- Lower trust: fan pages, forums, unsourced lists, social content.

Source-pack build process:

1. Normalize the theme.
2. Identify likely taxonomy.
3. Search configured sources.
4. Snapshot allowed source material.
5. Extract entities, aliases, dates, works, relationships, events, and notable terms.
6. Build embeddings for source chunks.
7. Deduplicate entities and aliases.
8. Assign trust and rights-risk scores.
9. Generate source-pack quality score.
10. Reject or quarantine source packs with insufficient evidence.

## 7. Taxonomy System

Taxonomy drives source selection, candidate generation, clue styles, validation rules, and rights checks.

Initial taxonomies:

- Music artist
- Album
- Song
- Film
- TV series
- Book
- Author
- Historical event
- Historical person
- Place
- Technical topic
- Classroom lesson
- General concept

Each taxonomy defines:

- Preferred source types.
- Entity schema.
- High-value answer types.
- Common clue angles.
- Rights risks.
- Difficulty heuristics.
- Validation rules.
- Fan-interest signals.

Music artist taxonomy:

- Entities: songs, albums, collaborators, bands, instruments, genres, labels, producers, tours, awards, birthplaces, eras.
- Fan-interest signals: notable tracks, live performances, recurring fan-favorite references, acclaimed albums, collaborations, signature phrases when safe.
- Rights policy: do not store or emit full lyrics. Use track titles, album titles, credited facts, public metadata, and short compliant references only when necessary.

Film and TV taxonomy:

- Entities: title, cast, characters, creators, episodes, settings, release dates, awards, production facts, notable scenes.
- Fan-interest signals: iconic moments, commonly referenced quotes, character relationships, episode names.
- Rights policy: avoid long script excerpts. Prefer paraphrase, character names, episode titles, and short compliant quote references where allowed.

Book taxonomy:

- Entities: author, title, characters, settings, chapters, themes, publication facts, public-domain excerpts when applicable.
- Rights policy: public-domain works can support richer excerpt use. Modern copyrighted works should use paraphrased facts and very short references only.

Technical/classroom taxonomy:

- Entities: key terms, definitions, prerequisites, examples, common mistakes, procedures, formulas, historical context.
- Validation focus: factual precision, pedagogical difficulty, and misconception avoidance.

Historical taxonomy:

- Entities: people, dates, locations, causes, consequences, primary sources, timelines, organizations.
- Validation focus: date accuracy, contested interpretations, and source trust.

## 8. Rights-Safe Content Policy

The system must handle copyrighted source material conservatively.

Hard rules:

- Do not ingest or store full copyrighted lyrics, scripts, poems, books, or long passages.
- Do not output long copyrighted quotes.
- Do not generate clues that depend on reconstructing a copyrighted passage.
- Do not use hidden prompts containing long copyrighted text as source context.
- Store source URLs, metadata, and short evidence snippets only.
- Prefer paraphrase and public facts over quotation.
- Keep rights metadata attached to every evidence item.
- Block publish when rights risk is above threshold.

Allowed examples:

- Song titles.
- Album titles.
- Publicly known credits.
- Release dates.
- Award facts.
- Names of collaborators.
- Short, policy-compliant quote references when necessary and allowed.
- Public-domain text excerpts.

Disallowed examples:

- Full lyrics.
- Verse or chorus reconstruction.
- Long movie or TV dialogue.
- Long passages from modern books.
- Generated paraphrases that are too close to a copyrighted passage.

Rights QA:

- Detect long quotes and quote-like passages.
- Check clue text against source snippets for excessive overlap.
- Flag lyrics/script/book-like content.
- Require provenance for all direct quotes.
- Apply stricter thresholds for music, film, TV, and modern books.

## 9. Model Routing And AI Governance

Use multiple model tiers instead of one model for everything.

Model tiers:

- Tier 0: deterministic code, heuristics, databases, regular validators.
- Tier 1: local embeddings and small local classifiers.
- Tier 2: local instruction models for extraction, clustering, candidate expansion, and cheap scoring.
- Tier 3: stronger local or cloud models for clue writing, ambiguity analysis, and repair.
- Tier 4: strongest reviewer model for final adversarial QA on puzzle finalists only.

Task routing:

| Task | Default tier | Escalation condition |
| --- | --- | --- |
| Taxonomy classification | Tier 1 or 2 | Low confidence or mixed taxonomy |
| Entity extraction | Tier 2 | Poor source quality or conflicting sources |
| Candidate expansion | Tier 2 | Sparse theme or weak candidate pool |
| Candidate deduplication | Tier 1 | High semantic similarity clusters |
| Grid construction | Tier 0 | None |
| Clue drafting | Tier 2 or 3 | Theme entries and hard clues |
| Clue rewrite | Tier 2 or 3 | Failed style or difficulty gate |
| Fact checking | Tier 1 plus Tier 2 | Conflicting evidence |
| Ambiguity review | Tier 3 | High-impact clues or low confidence |
| Rights review | Tier 1 plus deterministic | Any quote-like content |
| Final publish review | Tier 4 | Only puzzle finalists |

Model registry fields:

- `model_id`
- `provider`
- `deployment_type`
- `allowed_tasks`
- `privacy_level`
- `max_input_tokens`
- `max_output_tokens`
- `cost_per_token`
- `latency_budget_ms`
- `temperature_defaults`
- `fallback_models`
- `quality_thresholds`
- `prompt_template_versions`
- `eval_score_requirements`

Governance rules:

- No model can be used for a task unless the model registry allows it.
- Prompts are versioned.
- Model outputs are cached by normalized input, model version, prompt version, and parameters.
- Cloud models receive only the minimum source context needed for the task.
- High-risk content gets stricter routing and validation.
- Model promotion requires eval evidence, not intuition.

## 10. AI Efficiency Strategy

The system should be efficient by design, not by later cleanup.

Efficiency techniques:

- Cache all model outputs with stable hashes.
- Use deterministic validators before model validators.
- Use embeddings for retrieval and duplicate checks before LLM review.
- Generate many cheap candidates, then spend stronger models only on finalists.
- Batch similar extraction and scoring jobs.
- Use constrained output schemas to reduce repair calls.
- Reuse source packs across puzzle runs.
- Reuse clue candidates across grid attempts when still valid.
- Log quality contribution by model and stage.
- Track failed expensive calls and eliminate low-value prompts.

Cost metrics:

- Cost per generated puzzle.
- Cost per published puzzle.
- Cost per quarantined puzzle.
- Cost per pipeline stage.
- Tokens per accepted clue.
- Tokens per rejected clue.
- Escalation rate by task.
- Cache hit rate by task.
- Retry count by stage.
- Publish rate by taxonomy.

Optimization loop:

1. Measure every call.
2. Identify expensive repeated tasks.
3. Build eval sets from accepted and rejected examples.
4. Compare cheaper local routes against expensive routes.
5. Promote cheaper routes only if quality holds.
6. Distill only after labels and task boundaries are stable.

## 11. Distillation And Model Improvement

Do not start by fine-tuning. Start with instrumentation and evals.

Good distillation candidates:

- Taxonomy classification.
- Source trust scoring.
- Answer difficulty prediction.
- Clue ambiguity scoring.
- Clue-answer semantic match scoring.
- Rights-risk classification.
- Fill-quality scoring.
- Theme-consistency scoring.

Poor early distillation candidates:

- Full clue generation before style and quality targets are stable.
- Final publish review before the QA rubric is mature.
- Open-ended source research where source coverage changes frequently.

Distillation workflow:

1. Collect production examples with labels.
2. Separate labels by task and taxonomy.
3. Create frozen train, validation, and test splits.
4. Benchmark current route.
5. Train or fine-tune smaller specialist model.
6. Run offline evals.
7. Run shadow mode in production.
8. Promote only when quality, latency, and cost improve.
9. Keep rollback path to previous model route.

Promotion criteria:

- Meets or beats current route on frozen evals.
- Does not regress protected QA gates.
- Reduces latency or cost enough to justify maintenance.
- Has stable monitoring metrics in shadow mode.

## 12. Crossword Construction

Use deterministic solving for the grid. AI should not be trusted to directly invent valid grids.

American-style grid requirements:

- Rotational symmetry by default.
- Connected open-cell region.
- No unchecked letters.
- No duplicate answers.
- Minimum answer length enforced.
- Theme entries placed in symmetric or otherwise valid theme positions.
- Fill constrained by approved wordlists and answer database.
- Difficulty controls affect fill obscurity and clue style.

Grid generation process:

1. Select theme entries and alternates.
2. Normalize answer lengths.
3. Choose grid size and theme layout strategy.
4. Place theme entries.
5. Generate black-square pattern.
6. Fill remaining grid using wordlists and candidate pools.
7. Score fill quality.
8. Reject grids that fail hard constraints.
9. Keep top N grid candidates for clue generation.

Fill scoring factors:

- Word familiarity.
- Crossword acceptability.
- Obscurity.
- Duplicate roots.
- Offensive or sensitive terms.
- Abbreviations.
- Partial phrases.
- Foreign terms.
- Proper-noun density.
- Crossing fairness.

## 13. Clue Generation

Clue generation should be multi-candidate, source-backed, and heavily validated.

Clue styles:

- Direct
- Trivia
- Definition-only
- Cryptic-lite
- Classroom
- Easy
- Standard
- Expert

Clue generation process:

1. Retrieve answer-specific evidence.
2. Generate several clue angles.
3. Draft multiple clues per angle.
4. Normalize style and difficulty.
5. Validate clue-answer match.
6. Check ambiguity.
7. Check factual support.
8. Check rights safety.
9. Repair weak clues.
10. Select final clue.

Clue quality rules:

- Clue must uniquely point to the answer.
- Clue should not be solvable only by reading obscure private context unless classroom mode is selected.
- Clue must match configured difficulty.
- Factual clue must have evidence.
- Definition clue must use accepted meaning.
- Trivia clue must not hallucinate.
- Clue should avoid answer leakage unless style allows it.
- Clue should not duplicate another clue's wording or fact too closely.
- Clue should avoid awkward grammar and unnatural phrasing.

## 14. QA Pipeline

The QA pipeline is the most important part of the product. Fully automated publish requires strict gates.

Hard gates:

- Grid legality.
- Fill validity.
- Duplicate answer detection.
- Duplicate clue detection.
- Theme consistency.
- Source support for factual clues.
- Clue-answer correctness.
- Ambiguity threshold.
- Rights safety.
- Offensive content.
- Difficulty bounds.
- Export validity.

Soft scores:

- Theme delight.
- Clue elegance.
- Fill smoothness.
- Variety.
- Educational value.
- Fan relevance.
- Novelty.
- Puzzle flow.

Publish decision:

- Publish only if every hard gate passes and aggregate soft score exceeds threshold.
- Quarantine if any hard gate fails.
- Retry or repair only if the failure type is repairable within budget.
- Stop early if source-pack quality is too low.

Repair paths:

- Replace weak answer candidate.
- Regenerate clue with narrower evidence.
- Rewrite clue for style or difficulty.
- Swap fill answer.
- Rebuild grid from alternate theme set.
- Reject source pack if evidence is inadequate.

Quarantine reasons:

- Insufficient source support.
- Unsafe copyrighted content.
- Ambiguous clue.
- Invalid grid.
- Poor fill quality.
- Weak theme cohesion.
- Offensive or sensitive content.
- Model output malformed.
- Budget exceeded.

## 15. Observability

Every run should answer:

- What was generated?
- From what sources?
- Which models were used?
- How much did it cost?
- Which validations passed or failed?
- Why was it published or quarantined?
- Which stage caused retries?
- Which model outputs led to accepted artifacts?

Required dashboards or reports:

- Run summary.
- Source-pack quality.
- Model-call cost and latency.
- QA gate pass/fail rates.
- Publish rate by taxonomy.
- Quarantine reasons.
- Retry rates.
- Cache hit rates.
- Cost per published puzzle.
- Evals over time.

Structured logs:

- JSON logs by run ID.
- Stage start and finish events.
- Artifact IDs.
- Model-call IDs.
- Validation IDs.
- Error codes.

## 16. Evaluation Suite

Build evals before distillation and before broad model changes.

Golden source packs:

- Music artist.
- Album.
- Film.
- TV series.
- Book.
- Historical event.
- Programming topic.
- Classroom lesson.
- General concept.

Eval dimensions:

- Taxonomy accuracy.
- Entity extraction quality.
- Candidate relevance.
- Theme cohesion.
- Grid legality.
- Fill smoothness.
- Clue correctness.
- Clue ambiguity.
- Difficulty calibration.
- Rights safety.
- Cost.
- Latency.
- Publish rate.

Adversarial tests:

- Theme with ambiguous name.
- Theme with sparse data.
- Theme with many copyrighted quotes.
- Theme with offensive source terms.
- Conflicting sources.
- Fan page misinformation.
- Near-duplicate answers.
- Proper-noun-heavy fill.
- Easy clues that accidentally become expert-level.
- Expert clues that become unfair.

Regression rule:

- No model, prompt, source parser, or solver change can be promoted if it regresses hard gates on the frozen eval set.

## 17. Export Artifacts

Even though v1 is CLI-first, it should export artifacts that future apps can use.

Export formats:

- Puzzle JSON.
- Answer key JSON.
- QA scorecard JSON.
- Source map JSON.
- Model lineage JSON.
- PDF-ready layout data.
- Web-play payload.

Puzzle JSON should include:

- Grid dimensions.
- Cell blocks.
- Numbering.
- Across clues.
- Down clues.
- Answers.
- Theme metadata.
- Difficulty.
- Source-pack ID.
- Publish decision ID.

Do not include hidden copyrighted source content in public exports.

## 18. Enterprise Platform Architecture

The project should evolve from a single generator into an enterprise-grade AI generation platform. The generator is one application built on top of shared platform capabilities: orchestration, retrieval, model routing, policy enforcement, experiment tracking, observability, and evaluation.

Architecture split:

- Control plane: manages runs, source packs, prompt versions, model registry, policy registry, experiments, budgets, eval suites, publish decisions, and user-visible reports.
- Data plane: executes source ingestion, vector indexing, retrieval, grid solving, clue generation, validation, batch jobs, exports, and eval workloads.
- Artifact plane: stores immutable source snapshots, generated puzzles, model outputs, eval bundles, lineage reports, and export artifacts.
- Policy plane: enforces rights rules, source trust, prompt-injection controls, model allowlists, tool permissions, budget limits, and publish gates.

Enterprise capabilities:

- Durable workflow execution with retries, checkpoints, resumability, and idempotent stage outputs.
- Job scheduling for large batch runs, nightly evals, model bakeoffs, and source-pack refreshes.
- Multi-environment support: local development, staging, production, and offline research lab.
- Versioned registries for models, prompts, routes, source connectors, wordlists, taxonomy rules, and QA policies.
- Full lineage from final clue back to source evidence, retrieval calls, model calls, validators, repair attempts, and publish decision.
- Budget controls per run, taxonomy, model route, experiment, and batch.

Recommended platform defaults:

- Use Postgres as the source of truth for structured metadata.
- Use object storage for large immutable artifacts.
- Use a workflow engine such as Temporal or Prefect for durable jobs.
- Use Ray for large local or distributed batch inference and eval sweeps.
- Keep crossword-specific business logic independent of LangChain, LangGraph, LlamaIndex, or any single framework.

## 19. Vector And Knowledge Graph Retrieval

Vectors should be a core system primitive, not an optional helper. The system should combine vector search, lexical search, structured metadata, and graph relationships.

Initial vector store:

- Use Postgres plus pgvector first because the platform already depends on Postgres.
- Add HNSW indexes for low-latency approximate nearest-neighbor search.
- Add full-text indexes for lexical search.
- Use hybrid retrieval for most factual generation tasks.

Vector tables:

- `source_chunk_embeddings`: source text chunks, source metadata, taxonomy, trust score, rights risk, and embedding vector.
- `entity_embeddings`: people, places, works, songs, albums, characters, terms, aliases, and canonical IDs.
- `answer_candidate_embeddings`: semantic clustering, duplicate detection, theme relevance, and novelty.
- `clue_embeddings`: clue similarity, repeated clue-angle detection, style clustering, and answer-leakage checks.
- `puzzle_embeddings`: whole-puzzle similarity, novelty, regression analysis, and theme-family clustering.
- `failure_embeddings`: cluster quarantined runs and QA failures to discover systemic weaknesses.

Retrieval strategy:

- Use hybrid retrieval: dense vector search plus full-text search plus metadata filtering.
- Apply reciprocal-rank fusion or weighted rank fusion to combine retrievers.
- Use cross-encoder or stronger-model reranking for final evidence selection when quality matters.
- Use multi-hop retrieval for rich themes: theme to entity, entity to relationship, relationship to evidence, evidence to clue angle.
- Use taxonomy-specific retrievers so music, film, books, technical lessons, and historical subjects retrieve different evidence shapes.
- Use retrieval confidence as a hard input to publish decisions.

Knowledge graph:

- Store entities and relationships separately from source chunks.
- Track aliases, canonical IDs, entity type, source support, confidence, and taxonomy.
- Represent relationships such as collaborator-of, appeared-in, wrote, performed, influenced-by, member-of, located-in, released-on, character-in, and prerequisite-of.
- Use graph traversal to propose theme sets and clue angles.
- Use vector retrieval to recover evidence for graph-derived claims.

Retrieval QA:

- Measure recall@k for known facts.
- Measure evidence precision for generated clues.
- Track unsupported factual clue rate.
- Track source diversity.
- Track stale-source rate.
- Track retrieval latency and reranker cost.
- Quarantine puzzles when required facts cannot be retrieved with enough confidence.

Framework posture:

- Use LangChain only where it cleanly improves provider/tool integration.
- Use LangGraph for stateful agent workflows and critic/repair loops.
- Use LlamaIndex where its ingestion, indexing, query-engine, or retrieval-eval abstractions accelerate RAG experiments.
- Keep the platform's schemas, policies, and validators framework-neutral.

## 20. Workflow Orchestration And Distributed Execution

The generator needs workflow semantics because high-quality puzzle generation is long-running, retry-heavy, and stateful.

Workflow requirements:

- Every pipeline stage is idempotent.
- Every stage has typed inputs and outputs.
- Every stage can be retried independently.
- Failed stages preserve enough state for debugging and repair.
- Long runs can resume after process failure.
- Expensive intermediate artifacts are reused.
- Batch jobs can fan out and fan in.

Recommended orchestration layers:

- Durable workflow engine for production jobs, retries, schedules, and resumability.
- Ray for distributed batch processing, embedding jobs, model bakeoffs, eval sweeps, and GPU inference batching.
- Local single-process executor for development and small runs.

Workflow types:

- `BuildSourcePackWorkflow`
- `GeneratePuzzleWorkflow`
- `ValidatePuzzleWorkflow`
- `PublishPuzzleWorkflow`
- `BatchGenerationWorkflow`
- `ModelBakeoffWorkflow`
- `EvalSuiteWorkflow`
- `DistillationDatasetWorkflow`
- `SourceRefreshWorkflow`

Distributed execution requirements:

- Support batch generation across many themes.
- Support testing many model routes against the same source packs.
- Support GPU batching for embeddings, local model inference, clue generation, and judge models.
- Support checkpointed batch outputs.
- Support cancellation and budget-based early stopping.
- Support run-set comparison after batch completion.

## 21. Batch Generation And Model Experimentation

Batch generation should be a first-class product surface. This is both a production feature and an AI engineering learning engine.

Batch CLI commands:

```bash
crosswordai batch generate --themes themes.csv --strategy strategies.yaml --models models.yaml --max-cost 50
crosswordai batch evaluate --run-set <run_set_id> --eval-suite golden-v1
crosswordai experiments compare --run-set <run_set_id> --metrics publish_rate,cost,latency,ambiguity,rights_risk
crosswordai experiments leaderboard --taxonomy music_artist --metric quality_per_dollar
crosswordai models shadow --candidate-route route_b --baseline-route route_a --sample-size 500
```

Experiment dimensions:

- Model route.
- Prompt version.
- Retrieval strategy.
- Reranker.
- Source-pack version.
- Grid solver config.
- Clue style.
- Difficulty.
- Judge model.
- Rights policy threshold.
- Repair strategy.

Model responsibility strategies to test:

- Specialist pipeline: separate models for extraction, candidate generation, clue writing, clue criticism, rights review, and final publish review.
- Cheap-first cascade: local model drafts, stronger model repairs only failures.
- Debate pipeline: multiple clue writers propose, critics attack, final judge selects.
- Jury pipeline: several small judges vote, stronger model resolves ties.
- Self-play solver: one model writes clues, other models attempt to solve them; unsolved or overbroad clues fail.
- Adversarial editor: a model is explicitly tasked with finding hallucinations, source mismatch, unfair ambiguity, duplicate clue angles, and rights leakage.
- Bandit router: route tasks to models based on historical quality, cost, latency, and taxonomy-specific performance.
- Ensemble retrieval: compare lexical, vector, graph, and hybrid retrieval evidence before clue generation.

Experiment outputs:

- Publish rate.
- Hard-gate failure rate.
- Cost per published puzzle.
- Latency per published puzzle.
- Tokens per accepted clue.
- Repair success rate.
- Hallucination rate.
- Rights-risk rate.
- Ambiguity rate.
- Human spot-check score when available.
- Route recommendation.

## 22. LLMOps And Model Promotion

Treat prompts, routes, evals, and models as production assets.

LLMOps requirements:

- Prompt registry with semantic versions, owners, changelogs, and eval history.
- Model registry with allowed tasks, budget limits, quality thresholds, privacy level, and fallback routes.
- Route registry defining task-to-model policies and escalation behavior.
- Eval registry with frozen datasets, generated stress sets, and taxonomy-specific benchmarks.
- Judge registry with calibration records and known weaknesses.
- Dataset registry for source packs, wordlists, clue corpora, failure cases, and distillation sets.

Promotion workflow:

1. Create candidate prompt, model, retrieval policy, or route.
2. Run unit evals on targeted tasks.
3. Run frozen regression evals.
4. Run adversarial evals.
5. Run shadow-mode production batch.
6. Compare against baseline by quality, cost, latency, and failure modes.
7. Promote only if protected gates do not regress.
8. Keep rollback path.

Advanced LLMOps features:

- Prompt diff reports.
- Route diff reports.
- Eval failure clustering.
- Automatic postmortems for quarantined puzzles.
- Drift detection by taxonomy, source type, model, and clue style.
- Judge disagreement analysis.
- Quality-per-dollar leaderboard.
- Model cards for local and cloud models.
- Puzzle cards that summarize generation lineage, risk, QA scores, and source coverage.

## 23. Security And AI Safety

The source corpus is untrusted input. The system must treat every external document as data, never instructions.

Security controls:

- Prompt-injection detection for source documents.
- Strict separation between system instructions, task instructions, retrieved source text, and model outputs.
- Tool allowlists per workflow stage and agent.
- No arbitrary tool execution from model output.
- Secrets scanning before model calls and artifact exports.
- PII detection and redaction for user notes.
- Network allowlists for source connectors.
- Content hashing for source snapshots and generated artifacts.
- Role-based permissions for future hosted or multi-user deployments.

AI safety controls:

- Copyright-risk classifier plus deterministic overlap checks.
- Toxicity and offensive-fill detection.
- Sensitive-topic classifier.
- Hallucination and unsupported-claim detection.
- Source-poisoning detection for low-trust or contradictory sources.
- Refusal or quarantine behavior for unsafe themes.
- Stronger review for minors, medical, legal, political, extremist, or adult content.
- Output policy engine that can block publish independent of model confidence.

Red-team evals:

- Prompt-injection pages that try to override generation instructions.
- Sources containing hidden instructions.
- Fake fan pages with plausible misinformation.
- Themes likely to trigger lyric leakage.
- Themes likely to trigger offensive fill.
- Ambiguous names that cause entity confusion.
- User notes containing secrets or PII.
- Adversarial requests to produce copyrighted passages.

## 24. Deep Agentic Generation Systems

Use agents only where their statefulness and tool use create measurable value. The default pipeline should remain deterministic and typed, with agentic loops inside bounded stages.

Recommended agent roles:

- Research agent: builds and critiques source packs.
- Taxonomy agent: identifies theme type and required evidence schema.
- Candidate editor: proposes and ranks theme entries.
- Grid strategist: chooses theme layout strategy but does not directly invent final grids.
- Clue writer: drafts clue candidates from approved evidence.
- Clue critic: attacks clues for ambiguity, unsupported claims, style mismatch, and answer leakage.
- Rights reviewer: flags quote, lyric, script, and excerpt risk.
- Fact checker: verifies factual clues against retrieved evidence.
- Puzzle editor: reviews overall puzzle cohesion and clue variety.
- Final publisher: summarizes QA state but cannot override hard gates.

Agent design rules:

- Agents operate on typed artifacts, not free-form hidden state.
- Agents can propose changes, but deterministic validators decide hard gates.
- Agents must cite source evidence IDs for factual claims.
- Agent tools are allowlisted per role.
- Agent memory is scoped by run and stored as auditable artifacts.
- Agent loops have max-iteration, max-cost, and max-latency budgets.
- Agent disagreement is captured as eval data.

Useful agent patterns:

- Critic-repair loop for clues.
- Debate-and-judge for difficult theme entries.
- Self-play solving for clue ambiguity.
- Adversarial review before publish.
- Multi-agent source-pack critique for broad or ambiguous themes.
- Planner-executor pattern for batch experiment setup.

## 25. Advanced Product Reports And Bells And Whistles

These features make the system feel polished and give it a serious AI engineering surface area.

Advanced reports:

- Puzzle quality heatmap showing weak crossings, clue risk, source strength, ambiguity, and difficulty spikes.
- Clue lineage report linking each clue to evidence, retrieval calls, model calls, validators, repairs, and final decision.
- Source coverage report showing which theme areas are well-supported or weak.
- Model contribution report showing which model outputs survived to final artifacts.
- Quarantine postmortem explaining root cause and recommended repair.
- Batch leaderboard ranking routes by quality, cost, latency, and publish rate.
- Rights-risk report for media-heavy themes.
- Taxonomy drift report showing where a taxonomy needs better rules or sources.

Sophisticated product features:

- House-style engine that learns from a curated clue style guide.
- Fan-relevance scorer for music, media, sports, and fandom-heavy themes.
- Theme novelty scorer to avoid generic or overused entries.
- Synthetic theme generator for stress-testing sparse, ambiguous, and high-risk themes.
- Automatic clue diversity balancing across trivia, definition, wordplay, and source-backed facts.
- Difficulty curve shaping across the solve.
- Puzzle cards summarizing quality, provenance, model route, and publish risk.
- Model cards for every local/cloud model used by the platform.
- Replayable generation timeline for debugging and demos.

## 26. Implementation Tickets And Build Order

The ticket order should build the stable platform first, then retrieval and generation, then enterprise-scale experimentation. Each ticket should leave the repo in a working state.

### Ticket 1: Python Project Foundation

- Create Python package structure.
- Add CLI framework.
- Add config loading.
- Add local development settings.
- Add structured JSON logging.
- Add typed artifact IDs and run IDs.
- Add basic test harness.

Exit criteria:

- `crosswordai --help` works.
- A no-op command creates a run ID and structured log.
- Unit tests run locally.

### Ticket 2: Postgres, Migrations, And Object Storage

- Add Postgres schema migrations.
- Add object-storage abstraction.
- Add artifact metadata tables.
- Add immutable artifact write/read helpers.
- Add local development storage backend.

Exit criteria:

- A run can store and retrieve structured metadata plus an object artifact.
- Storage helpers are covered by tests.

### Ticket 3: Control Plane Registry Skeleton

- Add model registry.
- Add prompt registry.
- Add route registry.
- Add policy registry.
- Add source connector registry.
- Add wordlist registry.

Exit criteria:

- Registries load from versioned config.
- Invalid registry entries fail validation.
- CLI can inspect active registry versions.

### Ticket 4: Workflow Executor Interface

- Define workflow and stage interfaces.
- Add local executor.
- Add idempotent stage output tracking.
- Add retry metadata.
- Add checkpoint records.

Exit criteria:

- A toy multi-stage workflow can resume from a completed stage.
- Failed stages preserve structured failure reasons.

### Ticket 5: Source-Pack Schema And User-Notes Ingestion

- Implement `SourcePack`, `SourceDocument`, and `EvidenceSnippet`.
- Add user-note ingestion.
- Add source snapshot storage.
- Add source trust metadata.
- Add rights metadata.

Exit criteria:

- A source pack can be built from local notes.
- Source pack inspection shows documents, snippets, trust, rights metadata, and artifact links.

### Ticket 6: Rights And Safety Baseline

- Add copyrighted-content risk checks.
- Add quote-length and overlap checks.
- Add prompt-injection pattern checks.
- Add PII and secrets scanning for user notes.
- Add policy-gate result schema.

Exit criteria:

- Long lyrics, scripts, modern-book excerpts, secrets, and prompt-injection attempts are blocked or quarantined.
- Policy decisions are logged and attached to source-pack artifacts.

### Ticket 7: Vector Store Foundation

- Add pgvector support.
- Add embedding model adapter.
- Add source chunking.
- Add `source_chunk_embeddings`.
- Add vector search, lexical search, and metadata filtering.

Exit criteria:

- Source chunks can be embedded and queried.
- Hybrid retrieval returns cited evidence snippets.
- Retrieval tests cover vector, lexical, and metadata-filtered queries.

### Ticket 8: Knowledge Graph Foundation

- Add entity and relationship schemas.
- Add aliases and canonical IDs.
- Add source-supported relationship records.
- Add graph traversal helpers.

Exit criteria:

- A source pack can store entities and relationships.
- Graph traversal can propose evidence-backed clue angles.

### Ticket 9: Taxonomy Engine

- Implement taxonomy classification.
- Add taxonomy schemas for music artist, film, book, technical topic, classroom lesson, and historical subject.
- Add taxonomy-specific source and retrieval policies.

Exit criteria:

- Source packs are assigned taxonomy with confidence.
- Taxonomy drives entity schema, retrieval policy, and rights thresholds.

### Ticket 10: External Source Connectors

- Add Wikipedia connector.
- Add Wikidata-style structured metadata connector.
- Add MusicBrainz-style connector.
- Add public-domain/book metadata connector.
- Add connector trust and license metadata.

Exit criteria:

- Source packs can be built from user notes plus at least two external source types.
- Connectors snapshot source metadata and preserve provenance.

### Ticket 11: Retrieval Evaluation Harness

- Add retrieval eval schema.
- Add recall@k and evidence precision metrics.
- Add source diversity and stale-source metrics.
- Add retrieval failure clustering.

Exit criteria:

- Retrieval strategies can be compared on a fixed source-pack eval set.
- Retrieval regressions can fail CI or local gate commands.

### Ticket 12: Model Adapter And Routing Layer

- Add local model adapter.
- Add cloud model adapter abstraction.
- Add cache keyed by input, prompt, model, parameters, and route.
- Add task-based routing.
- Add budget and timeout enforcement.

Exit criteria:

- Mock, local, and cloud-capable model routes share the same interface.
- Model calls are cached and logged.
- Budget limits stop runaway jobs.

### Ticket 13: Prompt Templates And Structured Outputs

- Add prompt template versioning.
- Add JSON/schema-constrained output parsing.
- Add malformed-output repair path.
- Add prompt diff metadata.

Exit criteria:

- Prompt changes are versioned.
- Model output parsing failures are captured and repairable.

### Ticket 14: Answer Candidate Generation

- Generate answer candidates from entities, graph relationships, retrieval evidence, and taxonomy rules.
- Normalize answers.
- Score theme relevance, familiarity, novelty, rights risk, and difficulty.
- Deduplicate by exact match, alias, root, and embedding similarity.

Exit criteria:

- Candidate pools are source-backed and large enough for common 15x15 themes.
- Duplicate and weak candidates are filtered before grid solving.

### Ticket 15: Deterministic Grid Solver

- Integrate or implement American-style crossword construction.
- Add rotational symmetry, connectivity, checked-letter, minimum-length, and duplicate-answer validation.
- Add theme-entry placement.
- Add fill scoring.

Exit criteria:

- Legal grids can be generated from fixed theme entries.
- Invalid grids produce precise failure reasons.

### Ticket 16: Clue Generation Pipeline

- Generate clue angles.
- Generate multiple clues per answer.
- Retrieve answer-specific evidence.
- Support direct, trivia, definition-only, cryptic-lite, classroom, easy, standard, and expert styles.

Exit criteria:

- Each answer receives multiple clue candidates with evidence and model lineage.
- Clue outputs are schema-valid.

### Ticket 17: Clue QA And Repair

- Add clue-answer correctness checks.
- Add ambiguity checks.
- Add source-support checks.
- Add style and difficulty checks.
- Add answer-leakage and duplicate-clue checks.
- Add repair loops.

Exit criteria:

- Weak clues are repaired or quarantined.
- QA results attach to every clue candidate.

### Ticket 18: Agentic Critic Workflows

- Add bounded LangGraph-style stateful workflows for critic-repair loops.
- Add clue writer, clue critic, fact checker, rights reviewer, and puzzle editor roles.
- Add agent tool allowlists.
- Add max-cost, max-latency, and max-iteration budgets.

Exit criteria:

- Agent workflows operate on typed artifacts.
- Agents cannot override deterministic hard gates.
- Agent disagreement is recorded as eval data.

### Ticket 19: Publish Gate And Puzzle Exports

- Add hard-gate publish decision.
- Add soft scorecard.
- Add quarantine reasons.
- Add puzzle JSON, answer key JSON, source map, QA scorecard, and model lineage exports.

Exit criteria:

- No puzzle publishes with hard-gate failures.
- Exported artifacts exclude hidden copyrighted source content.

### Ticket 20: OpenTelemetry And LLMOps Observability

- Add trace spans per workflow, stage, model call, retrieval call, validator, and export.
- Add cost and latency rollups.
- Add model-call lineage.
- Add run inspection reports.

Exit criteria:

- A run can be inspected from puzzle back to source evidence and model calls.
- Cost, latency, retry count, cache hit rate, and QA gates are visible per run.

### Ticket 21: Evaluation Registry And Golden Sets

- Add eval registry.
- Add frozen golden source packs.
- Add taxonomy-specific evals.
- Add adversarial evals for injection, misinformation, ambiguity, rights leakage, and offensive fill.

Exit criteria:

- Evals can compare two routes.
- Protected hard-gate regressions fail promotion.

### Ticket 22: Batch Generation Engine

- Add batch run-set schema.
- Add batch CLI commands.
- Add fan-out/fan-in execution.
- Add checkpointed batch outputs.
- Add cancellation and budget stopping.

Exit criteria:

- The system can generate puzzles for many themes in one run.
- Batch results are inspectable and reproducible.

### Ticket 23: Model Bakeoff And Experimentation

- Add experiment matrix runner for models, prompts, routes, retrieval strategies, judge models, and repair strategies.
- Add route comparison reports.
- Add leaderboard by taxonomy and metric.

Exit criteria:

- Multiple model-responsibility strategies can be tested on the same source packs.
- Reports compare quality, cost, latency, publish rate, and failure modes.

### Ticket 24: Distributed Batch And GPU Throughput

- Add Ray-backed executor for embedding, model inference, eval sweeps, and large batch generation.
- Add GPU batching controls.
- Add worker health and retry reporting.

Exit criteria:

- Batch evals can scale beyond a single local process.
- Throughput, cost, and failure metrics are captured by worker and task type.

### Ticket 25: Advanced Model Routing

- Add shadow mode.
- Add jury routing.
- Add debate routing.
- Add cheap-first cascade routing.
- Add self-play solver checks.
- Add bandit-routing experiment support.

Exit criteria:

- Advanced routes can run in batch without replacing baseline production routes.
- Shadow-mode reports show whether candidate routes should be promoted.

### Ticket 26: Distillation Dataset Pipeline

- Convert accepted, rejected, repaired, and quarantined artifacts into labeled datasets.
- Add train/validation/test split creation.
- Add dataset cards.
- Add task-specific export formats.

Exit criteria:

- At least one specialist task has a frozen dataset ready for fine-tuning or classifier training.
- Dataset lineage points back to source packs and QA decisions.

### Ticket 27: Model Promotion And Rollback

- Add promotion workflow for prompts, models, routes, retrieval policies, and judges.
- Add shadow-mode requirement.
- Add rollback metadata.
- Add promotion reports.

Exit criteria:

- No route can be promoted without eval evidence.
- Rollback target is always recorded.

### Ticket 28: Enterprise Reports And Bells And Whistles

- Add puzzle quality heatmap.
- Add clue lineage report.
- Add source coverage report.
- Add quarantine postmortem.
- Add model contribution report.
- Add puzzle cards and model cards.

Exit criteria:

- A generated puzzle has a polished inspection bundle suitable for demos, debugging, and future UI surfaces.

### Ticket 29: Production Hardening

- Add network allowlists for connectors.
- Add secrets management integration.
- Add environment separation.
- Add role/permission model for future hosted deployment.
- Add backup and retention policy.
- Add disaster-recovery notes.

Exit criteria:

- The platform has a credible path from local CLI to staged production deployment.

## 27. Initial Acceptance Tests

Minimum tests before calling v1 production-ready:

- Build source pack for a music artist and verify entities include albums, songs, collaborators, genres, and source evidence.
- Build source pack for a film and verify cast, characters, release facts, and quote-risk handling.
- Build source pack for a classroom lesson and verify key terms, definitions, and misconception checks.
- Generate a 15x15 American-style puzzle from a fixed source pack and fixed seed.
- Confirm generated grid is connected, symmetric, checked, and duplicate-free.
- Confirm every factual clue has evidence.
- Confirm no long lyrics, scripts, or modern-book passages appear in generated artifacts.
- Confirm ambiguous clues are quarantined or repaired.
- Confirm model calls are logged with prompt version, model ID, token counts, latency, and cost.
- Confirm repeated run with same versions and seed is reproducible.
- Confirm failed publish emits exact hard-gate failure reasons.
- Confirm export JSON excludes hidden source text.
- Confirm hybrid retrieval returns source-backed evidence and records retrieval scores.
- Confirm knowledge graph relationships can support theme-entry and clue-angle generation.
- Confirm prompt-injection content inside sources is treated as untrusted data.
- Confirm batch generation can run multiple themes and multiple model routes.
- Confirm model bakeoff reports compare quality, cost, latency, publish rate, and failure modes.
- Confirm shadow-mode routes can run without replacing the baseline route.
- Confirm OpenTelemetry traces connect workflow stages, retrieval calls, model calls, validators, and final artifacts.
- Confirm advanced agentic critic loops cannot override deterministic hard gates.
- Confirm distillation datasets can be created from accepted, rejected, repaired, and quarantined artifacts.
- Confirm promotion requires eval evidence and records rollback metadata.

## 28. Open Engineering Decisions

These are implementation choices that should be decided during the early foundation tickets, after quick prototypes:

- Whether to build a custom grid solver or integrate an existing crossword construction library.
- Whether the durable workflow engine should be Temporal, Prefect, or a lighter custom executor for v1.
- Whether Ray should be introduced immediately for batch jobs or after the local executor proves the pipeline.
- Whether pgvector is enough through v1 or a dedicated vector database should be evaluated later.
- Whether LangGraph should be the default agent workflow layer or limited to experimental critic loops first.
- Whether LangChain should be used for provider integrations or avoided in favor of direct model adapters.
- Whether LlamaIndex should be used for ingestion/retrieval experiments or only as a research harness.
- Which local embedding model to use first.
- Which local instruction model to use first on the target hardware.
- Which cloud model is allowed for Tier 4 final review.
- Which judge models are reliable enough for promotion decisions.
- Which wordlists and crossword answer databases are licensed or acceptable for use.
- Which object storage backend to use locally during development.
- Which source APIs have acceptable terms for metadata ingestion.
- Which observability stack to use for OpenTelemetry traces and dashboards.
- Which eval sets are protected gates versus research-only benchmarks.
- Which model-responsibility strategies should become baseline candidates after initial bakeoffs.

Default choices until replaced:

- Prefer existing solver libraries if they satisfy American-style constraints and can be inspected.
- Prefer a local executor first, then add durable orchestration before long-running batch workflows become complex.
- Prefer pgvector for v1 retrieval unless scale or ranking quality proves it insufficient.
- Prefer LangGraph for bounded agentic critic/repair loops, not for the whole deterministic pipeline.
- Prefer framework-neutral core schemas and direct validators over framework-owned abstractions.
- Prefer local models for extraction, scoring, and retrieval.
- Reserve cloud models for final review, difficult clue writing, and low-confidence ambiguity checks.
- Prefer MinIO-compatible object storage for local development if object storage is needed before deployment.
- Prefer permissively licensed wordlists and explicitly documented source metadata.
