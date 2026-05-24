from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.batch import BatchExecutionPolicy, BatchRunSet, LocalBatchExecutor, inspect_batch_run_set
from crosswordai.clues import ClueCandidate
from crosswordai.datasets import (
    LabeledExample,
    build_dataset_from_lifecycle_artifacts,
    dataset_card_payload,
    export_openai_chat_jsonl,
    split_examples,
)
from crosswordai.distributed import (
    DistributedTask,
    GPUBatchingConfig,
    LocalDistributedExecutor,
    WorkerSpec,
    throughput_report_payload,
)
from crosswordai.evals import (
    EvalRegistry,
    ProtectedRegressionError,
    RouteScore,
    assert_no_protected_regressions,
    build_adversarial_suite,
    compare_eval_runs,
    compare_routes,
    evaluate_route_outputs,
)
from crosswordai.experiments import ExperimentMatrix, ExperimentMatrixRunner
from crosswordai.exports import export_bundle
from crosswordai.hardening import (
    BackupPolicy,
    DisasterRecoveryPlan,
    EnvironmentConfig,
    NetworkAllowlist,
    SecretRef,
    assess_production_readiness,
    default_permission_policy,
    production_readiness_payload,
)
from crosswordai.metadata import LocalMetadataStore
from crosswordai.models import ModelCallRecord
from crosswordai.observability import TraceRecorder, inspect_run
from crosswordai.promotion import PromotionCandidate, PromotionGate, PromotionWorkflow, promotion_report_payload
from crosswordai.qa import PublishDecision, QAScorecard
from crosswordai.reports import (
    enterprise_inspection_bundle,
    puzzle_card,
    quarantine_postmortem,
    report_export_payload,
)
from crosswordai.routing import AdvancedRouteExecutor, DEFAULT_ADVANCED_ROUTES
from crosswordai.solver import Grid
from crosswordai.storage import LocalArtifactStore


class EnterpriseSurfaceTests(unittest.TestCase):
    def test_trace_recorder_records_span(self) -> None:
        recorder = TraceRecorder()
        with recorder.span("model_call", task="qa"):
            pass
        self.assertEqual(recorder.spans[0].name, "model_call")
        self.assertEqual(recorder.spans[0].attributes["task"], "qa")

    def test_run_inspection_rolls_up_model_retrieval_and_export_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            metadata = LocalMetadataStore(tmp_path / "crosswordai.db")
            artifact_store = LocalArtifactStore(tmp_path / "artifacts")
            metadata.create_run(run_id="run_obs", run_type="inspection_test")
            artifact = artifact_store.write_json({"ok": True})
            metadata.record_artifact(run_id="run_obs", artifact=artifact)
            metadata.record_model_call(
                ModelCallRecord(
                    id="mc_1",
                    run_id="run_obs",
                    task_type="clue_generation",
                    model_id="mock-local",
                    route_id="baseline-local",
                    prompt_hash="p",
                    output_hash="o",
                    latency_ms=12.0,
                    input_tokens=10,
                    output_tokens=5,
                    estimated_cost=0.015,
                    cache_hit=True,
                    retry_count=1,
                    created_at="2026-05-21T00:00:00+00:00",
                )
            )
            trace = TraceRecorder()
            trace.record_retrieval_call(query="Miles Davis", result_count=3, latency_ms=7.0)
            trace.record_export(artifact_type="public_puzzle", status="published", latency_ms=2.0)
            report = inspect_run(run_id="run_obs", metadata_store=metadata, trace=trace)
            self.assertEqual(report.rollup.model_call_count, 1)
            self.assertEqual(report.rollup.retrieval_call_count, 1)
            self.assertEqual(report.rollup.export_count, 1)
            self.assertEqual(report.rollup.cache_hit_rate, 1.0)
            self.assertEqual(len(report.artifacts), 1)

    def test_route_comparison_prefers_quality_per_dollar(self) -> None:
        scores = compare_routes(
            [
                RouteScore("expensive", quality=0.9, cost=9.0, latency_ms=1000, publish_rate=0.9),
                RouteScore("cheap", quality=0.8, cost=1.0, latency_ms=500, publish_rate=0.8),
            ]
        )
        self.assertEqual(scores[0].route_id, "cheap")

    def test_eval_registry_compares_routes_and_blocks_protected_regressions(self) -> None:
        registry = EvalRegistry.load(Path("evals/registry.json"))
        suite = registry.get("golden-crossword-v1")
        baseline = evaluate_route_outputs(
            route_id="baseline",
            suite=suite,
            outputs={
                "music_publish_gate": {"status": "published", "raw_evidence_quotes_included": "false"},
                "technical_clue_support": {"qa_status": "passed"},
            },
        )
        candidate = evaluate_route_outputs(
            route_id="candidate",
            suite=suite,
            outputs={
                "music_publish_gate": {"status": "published", "raw_evidence_quotes_included": "true"},
                "technical_clue_support": {"qa_status": "passed"},
            },
        )
        comparison = compare_eval_runs(baseline=baseline, candidate=candidate)
        self.assertFalse(comparison.promotion_safe)
        self.assertEqual(comparison.winner, "baseline")
        with self.assertRaises(ProtectedRegressionError):
            assert_no_protected_regressions(candidate)
        adversarial = build_adversarial_suite()
        self.assertIn("rights_leakage", {case.adversarial_tags[0] for case in adversarial.cases if case.adversarial_tags})

    def test_export_bundle_enforces_publish_gate_and_excludes_evidence_quotes(self) -> None:
        grid = Grid(("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"))
        clue = ClueCandidate(
            "ABCDE",
            "Evidence-backed clue",
            "direct",
            "easy",
            ("ev1",),
            0.1,
            0.9,
            "low",
            "passed",
            evidence_quotes=("copyright-sensitive quote should not export",),
            model_lineage=("mock-local",),
        )
        decision = PublishDecision("published", (), QAScorecard((), 0.95))
        bundle = export_bundle(
            puzzle_id="p1",
            grid=grid,
            clues=[clue],
            publish_decision=decision,
            source_pack_id="sp1",
            run_id="run1",
        )
        self.assertTrue(bundle["hard_gate_enforced"])
        self.assertNotIn("copyright-sensitive", str(bundle))
        self.assertEqual(bundle["artifacts"]["public_puzzle"]["export_policy"]["raw_evidence_quotes_included"], False)

    def test_batch_run_set_crosses_themes_and_routes(self) -> None:
        run_set = BatchRunSet.create("batch_1", ["Miles", "Python"], ["a", "b"])
        self.assertEqual(len(run_set.items), 4)
        self.assertEqual(run_set.summary()["pending"], 4)

    def test_batch_executor_writes_checkpoints_and_inspection_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_set = BatchRunSet.create("batch_exec", ["Miles", "Python"], ["baseline"])
            executor = LocalBatchExecutor(
                LocalArtifactStore(Path(tmp) / "artifacts"),
                policy=BatchExecutionPolicy(max_cost=1.0),
            )
            report = executor.execute(run_set)
            inspection = inspect_batch_run_set(run_set)
            self.assertEqual(report.summary["succeeded"], 2)
            self.assertEqual(len(report.checkpoint_refs), 2)
            self.assertEqual(len(inspection.outputs), 2)
            self.assertTrue(inspection.reproducibility_hash)

    def test_experiment_matrix_runner_builds_taxonomy_leaderboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            matrix = ExperimentMatrix.from_axes(
                id="exp_1",
                models=("mock-local", "mock-large"),
                prompts=("clue_candidate",),
                routes=("baseline-local", "cheap_first_cascade"),
                retrieval_strategies=("hybrid",),
                judge_models=("mock-local",),
                repair_strategies=("deterministic",),
                source_pack_refs=("fixture://sp1", "fixture://sp2"),
                taxonomy="music_artist",
            )
            report = ExperimentMatrixRunner(artifact_store=LocalArtifactStore(Path(tmp) / "artifacts")).run(matrix)
            self.assertEqual(len(report.results), 4)
            self.assertIn("music_artist", report.taxonomy_leaderboards)
            self.assertTrue(report.winner_route_id)
            self.assertTrue(report.artifact_ref)

    def test_local_distributed_executor_tracks_worker_health_and_throughput(self) -> None:
        executor = LocalDistributedExecutor(
            (
                WorkerSpec(
                    "worker_1",
                    ("embedding", "eval"),
                    max_concurrency=2,
                    gpu=GPUBatchingConfig(enabled=True, max_batch_size=8, target_device="cuda:0", precision="fp16"),
                ),
            )
        )
        tasks = (
            DistributedTask("task_1", "embedding", {"text": "Miles"}),
            DistributedTask("task_2", "eval", {"suite": "golden"}),
        )
        benchmark = executor.benchmark(tasks)
        payload = throughput_report_payload(benchmark)
        self.assertEqual(benchmark.succeeded, 2)
        self.assertEqual(benchmark.worker_health[0].completed_tasks, 2)
        self.assertTrue(payload["gpu_config"]["enabled"])

    def test_advanced_routes_registered(self) -> None:
        self.assertIn("cheap_first_cascade", {route.id for route in DEFAULT_ADVANCED_ROUTES})

    def test_advanced_route_executor_supports_shadow_cascade_and_bandit(self) -> None:
        executor = AdvancedRouteExecutor(quality_threshold=0.7)
        cascade = executor.execute(
            "cheap_first_cascade",
            {"answer": "MILES"},
            baseline_route_id="baseline-local",
            candidate_route_ids=("mock-large",),
        )
        self.assertEqual(cascade.status, "selected")
        self.assertTrue(cascade.promotion_evidence["option_count"])
        shadow_decision, shadow_report = executor.shadow(
            payload={"answer": "MILES"},
            baseline_route_id="baseline-local",
            candidate_route_id="mock-large",
        )
        self.assertEqual(shadow_decision.status, "shadow_only")
        self.assertEqual(shadow_decision.selected_route_id, "baseline-local")
        self.assertIn("promote", shadow_decision.promotion_evidence)
        bandit = executor.execute("bandit_router", {"answer": "MILES"}, candidate_route_ids=("route_a", "route_b"))
        self.assertEqual(bandit.status, "selected")
        self.assertIn("bandit_state", bandit.promotion_evidence)
        self.assertEqual(shadow_report.baseline_route_id, "baseline-local")

    def test_dataset_split_is_deterministic(self) -> None:
        examples = [LabeledExample(str(i), "qa", "in", "out", "accepted", "decision") for i in range(10)]
        train, validation, test = split_examples(examples)
        self.assertEqual(len(train), 7)
        self.assertEqual(len(validation), 1)
        self.assertEqual(len(test), 2)

    def test_distillation_dataset_builds_lineage_and_task_exports(self) -> None:
        dataset, report = build_dataset_from_lifecycle_artifacts(
            dataset_id="clue_qa_v1",
            task_type="clue_qa",
            version="1",
            artifacts=[
                {
                    "id": "a1",
                    "status": "published",
                    "input_ref": "input://accepted",
                    "output_ref": "output://accepted",
                    "source_pack_id": "sp1",
                    "run_id": "run1",
                },
                {
                    "id": "a2",
                    "status": "quarantined",
                    "input_ref": "input://quarantined",
                    "output_ref": "output://quarantined",
                    "source_pack_id": "sp1",
                    "qa_decision_ref": "qa2",
                },
                {
                    "id": "a3",
                    "status": "failed",
                    "input_ref": "input://rejected",
                    "output_ref": "output://rejected",
                    "source_pack_id": "sp2",
                },
            ],
        )
        card = dataset_card_payload(dataset)
        chat_jsonl = export_openai_chat_jsonl(dataset.examples)
        self.assertEqual(report.example_count, 3)
        self.assertEqual(dataset.card.label_counts["accepted"], 1)
        self.assertEqual(dataset.card.label_counts["quarantined"], 1)
        self.assertIn("sp1", dataset.card.lineage_refs)
        self.assertEqual(card["dataset_id"], "clue_qa_v1")
        self.assertIn('"messages"', chat_jsonl)

    def test_promotion_gate_requires_no_regressions(self) -> None:
        decision = PromotionGate().decide(
            PromotionCandidate("route", "route_b", "route_a", "eval_1", 0, "route_a")
        )
        self.assertEqual(decision.status, "approved")
        rejected = PromotionGate().decide(
            PromotionCandidate("route", "route_b", "route_a", "eval_1", 1, "route_a")
        )
        self.assertEqual(rejected.status, "rejected")

    def test_promotion_workflow_requires_shadow_for_routes_and_records_rollback(self) -> None:
        missing_shadow = PromotionWorkflow().run(
            PromotionCandidate("route", "route_b", "route_a", "eval_1", 0, "route_a")
        )
        self.assertEqual(missing_shadow.decision.status, "rejected")
        self.assertIn("missing_shadow_mode_report", missing_shadow.decision.reasons)
        approved = PromotionWorkflow().run(
            PromotionCandidate(
                "route",
                "route_b",
                "route_a",
                "eval_1",
                0,
                "route_a",
                shadow_report_ref="shadow://route_b",
            )
        )
        payload = promotion_report_payload(approved)
        self.assertEqual(approved.decision.status, "approved")
        self.assertEqual(approved.rollback_plan.rollback_target, "route_a")
        self.assertEqual(payload["rollback_plan"]["registry_mutations"][1]["action"], "rollback")

    def test_reports_and_hardening(self) -> None:
        decision = PublishDecision("quarantined", ("ambiguous_clue",), QAScorecard(("ambiguous_clue",), 0.2))
        self.assertEqual(puzzle_card(puzzle_id="p1", theme="Jazz", decision=decision, model_route="r")["status"], "quarantined")
        self.assertEqual(quarantine_postmortem(decision)["recommended_action"], "repair_or_regenerate")
        self.assertTrue(NetworkAllowlist({"example.com"}).validate_url("https://example.com/a").passed)
        self.assertFalse(NetworkAllowlist({"example.com"}).validate_url("https://bad.test/a").passed)

    def test_enterprise_inspection_bundle_contains_demo_surfaces(self) -> None:
        grid = Grid(("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"))
        clue = ClueCandidate(
            "ABCDE",
            "Evidence-backed clue",
            "direct",
            "easy",
            ("ev1",),
            0.1,
            0.9,
            "low",
            "passed",
            model_lineage=("mock-local",),
        )
        decision = PublishDecision("published", (), QAScorecard((), 0.95, metrics={"clue_pass_rate": 1.0}))
        bundle = enterprise_inspection_bundle(
            puzzle_id="p1",
            theme="Demo",
            grid=grid,
            clues=[clue],
            decision=decision,
            source_pack_id="sp1",
            model_route="baseline-local",
            baseline_taxonomy="music_artist",
            observed_taxonomies=("music_artist", "music_artist"),
        )
        payload = report_export_payload(bundle)
        self.assertEqual(len(bundle.quality_heatmap), 25)
        self.assertEqual(bundle.source_coverage[0].evidence_id, "ev1")
        self.assertEqual(bundle.model_cards[0].model_id, "mock-local")
        self.assertFalse(bundle.taxonomy_drift.warnings)
        self.assertIn("clue_lineage", payload)

    def test_production_readiness_report_covers_hardening_controls(self) -> None:
        report = assess_production_readiness(
            environment=EnvironmentConfig(
                name="prod",
                database_url="postgresql://db/crosswordai",
                artifact_root="s3://crosswordai-prod",
                allowed_hosts=("example.com",),
                secrets_provider="env",
                debug=False,
            ),
            secrets=(SecretRef("OPTIONAL_KEY", "env", required=False),),
            backup_policy=BackupPolicy(
                enabled=True,
                schedule="daily",
                retention_days=30,
                artifact_retention_days=90,
                restore_test_interval_days=14,
            ),
            disaster_recovery=DisasterRecoveryPlan(
                rpo_minutes=30,
                rto_minutes=120,
                runbook_ref="docs/dr.md",
                escalation_contacts=("ops@example.com",),
                last_drill_at="2026-05-21",
            ),
            permission_policy=default_permission_policy(),
            egress_urls=("https://example.com/api",),
        )
        payload = production_readiness_payload(report)
        self.assertTrue(report.passed)
        self.assertEqual(payload["environment"], "prod")
        self.assertIn("backup_policy", payload["controls"])


if __name__ == "__main__":
    unittest.main()
