from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.cli import main
from crosswordai.config import Settings
from crosswordai.ids import ArtifactId, new_artifact_id, new_run_id
from crosswordai.metadata import LocalMetadataStore, metadata_store_from_settings
from crosswordai.migrations import MigrationRunner
from crosswordai.registries import load_registries
from crosswordai.storage import ArtifactExistsError, LocalArtifactStore, ObjectStoreNotConfiguredError, S3ArtifactStore
from crosswordai.workflows import LocalWorkflowExecutor, StageResult


class FoundationTests(unittest.TestCase):
    def test_ids_have_expected_prefixes(self) -> None:
        self.assertTrue(str(new_run_id()).startswith("run_"))
        self.assertTrue(str(new_artifact_id()).startswith("art_"))

    def test_local_artifact_store_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalArtifactStore(Path(tmp))
            artifact_id = ArtifactId("art_20260101000000_fixed")
            store.write_json({"ok": True}, artifact_id=artifact_id)
            self.assertEqual(store.read_json(artifact_id), {"ok": True})
            with self.assertRaises(ArtifactExistsError):
                store.write_json({"ok": False}, artifact_id=artifact_id)

    def test_registries_load(self) -> None:
        registries = load_registries(Path("config/registries"))
        self.assertIn("mock-local", registries["models"].active_versions())
        self.assertIn("rights-safe-v1", registries["policies"].active_versions())
        self.assertIn("wikipedia", registries["source_connectors"].active_versions())
        self.assertIn("musicbrainz", registries["source_connectors"].active_versions())
        self.assertIn("clue_candidate_v1", registries["output_schemas"].active_versions())

    def test_invalid_registry_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["models", "prompts", "routes", "policies", "source_connectors", "wordlists", "output_schemas"]:
                (root / f"{name}.json").write_text("[]", encoding="utf-8")
            (root / "models.json").write_text('[{"id": "missing-version"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_registries(root)

    def test_noop_cli_creates_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "settings.json"
            config_path.write_text(
                json.dumps({"home": str(Path(tmp) / "home"), "artifact_root": str(Path(tmp) / "artifacts")}),
                encoding="utf-8",
            )
            self.assertEqual(main(["--config", config_path.as_posix(), "noop"]), 0)
            self.assertTrue(any((Path(tmp) / "artifacts").glob("art_*.json")))
            self.assertTrue((Path(tmp) / "home" / "crosswordai.db").exists())

    def test_batch_cli_creates_run_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            themes = tmp_path / "themes.txt"
            themes.write_text("Miles Davis\nPython\n", encoding="utf-8")
            config_path = tmp_path / "settings.json"
            config_path.write_text(
                json.dumps({"home": str(tmp_path / "home"), "artifact_root": str(tmp_path / "artifacts")}),
                encoding="utf-8",
            )
            self.assertEqual(
                main(
                    [
                        "--config",
                        config_path.as_posix(),
                        "batch",
                        "generate",
                        "--themes",
                        themes.as_posix(),
                        "--routes",
                        "a,b",
                    ]
                ),
                0,
            )
            self.assertTrue(any((tmp_path / "artifacts").glob("art_*.json")))

    def test_retrieval_eval_cli_passes_fixture_suite(self) -> None:
        self.assertEqual(
            main(["retrieval", "eval", "--suite", "evals/retrieval/golden-v1.json", "--k", "1"]),
            0,
        )

    def test_local_metadata_store_records_run_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            store = LocalArtifactStore(tmp_path / "artifacts")
            metadata = LocalMetadataStore(tmp_path / "crosswordai.db")
            metadata.create_run(run_id="run_test", run_type="unit")
            artifact = store.write_json({"ok": True})
            metadata.record_artifact(run_id="run_test", artifact=artifact)
            completed = metadata.complete_run(run_id="run_test")
            self.assertEqual(completed.status, "succeeded")
            self.assertEqual(len(metadata.list_artifacts(run_id="run_test")), 1)

    def test_metadata_store_factory_rejects_postgres_until_adapter_exists(self) -> None:
        class Settings:
            database_url = "postgresql://localhost/crosswordai"
            metadata_db = Path("unused.db")

        with self.assertRaises(RuntimeError) as context:
            metadata_store_from_settings(Settings())
        self.assertIn("psycopg", str(context.exception))

    def test_migration_runner_loads_and_runs_sql(self) -> None:
        class Executor:
            def __init__(self) -> None:
                self.scripts: list[str] = []

            def execute_script(self, sql: str) -> None:
                self.scripts.append(sql)

        executor = Executor()
        applied = MigrationRunner(Path("migrations")).run(executor)
        self.assertIn("0001", applied)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS runs" in script for script in executor.scripts))
        self.assertTrue(any("retrieval_traces" in script for script in executor.scripts))
        self.assertTrue(any("graph_entities" in script for script in executor.scripts))
        self.assertTrue(any("taxonomy_metadata_json" in script for script in executor.scripts))
        self.assertTrue(any("model_calls" in script for script in executor.scripts))

    def test_s3_artifact_store_requires_optional_dependency(self) -> None:
        try:
            import boto3  # type: ignore[import-not-found]  # noqa: F401
        except ModuleNotFoundError:
            with self.assertRaises(ObjectStoreNotConfiguredError):
                S3ArtifactStore(bucket="crosswordai")

    def test_workflow_executor_resumes_completed_stage_and_stops_on_failure(self) -> None:
        calls: list[str] = []

        class Stage:
            def __init__(self, name: str, status: str = "succeeded") -> None:
                self.name = name
                self.status = status

            def run(self, context: dict[str, object]) -> StageResult:
                calls.append(self.name)
                return StageResult(
                    self.name,
                    self.status,
                    {"ran": self.name},
                    None if self.status == "succeeded" else "planned failure",
                )

        executor = LocalWorkflowExecutor()
        first = executor.run([Stage("one"), Stage("two", "failed"), Stage("three")])
        self.assertEqual([result.name for result in first], ["one", "two"])
        self.assertEqual(first[-1].failure_reason, "planned failure")
        second = executor.run([Stage("one"), Stage("two", "failed")])
        self.assertEqual([result.name for result in second], ["one", "two"])
        self.assertEqual(calls, ["one", "two"])


if __name__ == "__main__":
    unittest.main()
