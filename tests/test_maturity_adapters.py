from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.graph import Entity, KnowledgeGraph
from crosswordai.hardening import (
    BackupPolicy,
    DeploymentManifest,
    DisasterRecoveryPlan,
    EnvironmentConfig,
    ManagedSecretManager,
    SecretRef,
    StaticManagedSecretProvider,
    validate_deployment_manifest,
)
from crosswordai.ids import ArtifactId, SourcePackId
from crosswordai.metadata import PostgresMetadataStore
from crosswordai.models import ModelCallRecord
from crosswordai.observability import (
    OTelExporterConfig,
    OTelTraceExporter,
    TraceRecorder,
    correlate_trace,
    dashboard_metrics_payload,
    default_alert_rules,
    otlp_payload,
)
from crosswordai.sources import EvidenceSnippet, SourceDocument, SourcePack
from crosswordai.storage import ArtifactRecord, S3ArtifactStore, signed_export_manifest, verify_artifact_signature


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.connection.executed.append((sql, params or ()))

    def fetchone(self) -> tuple[object, ...] | None:
        return self.connection.fetchone_queue.pop(0) if self.connection.fetchone_queue else (1,)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.connection.fetchall_queue.pop(0) if self.connection.fetchall_queue else []


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetchone_queue: list[tuple[object, ...] | None] = []
        self.fetchall_queue: list[list[tuple[object, ...]]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


class FakePsycopg:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self, database_url: str) -> FakeConnection:
        return self.connection


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.checked_bucket: str | None = None

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, io.BytesIO]:
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_bucket(self, *, Bucket: str) -> None:
        self.checked_bucket = Bucket


class MaturityAdapterTests(unittest.TestCase):
    def test_postgres_adapter_records_source_pack_graph_and_model_calls(self) -> None:
        connection = FakeConnection()
        store = PostgresMetadataStore("postgresql://db/crosswordai", psycopg_module=FakePsycopg(connection))
        artifact = ArtifactRecord(ArtifactId("art_20260101000000_pg"), "application/json", Path("s3://bucket/source.json"), "2026-01-01")
        document = SourceDocument(
            "doc1",
            "sp_20260101000000_pg",
            "user_notes",
            "notes.md",
            "notes",
            "user",
            "2026-01-01",
            "user_provided",
            0.95,
            "hash",
            "s3://bucket/notes.txt",
        )
        snippet = EvidenceSnippet("ev1", "doc1", "Miles Davis source evidence.", 0, 28, "hash", "low", "internal_evidence")
        source_pack = SourcePack(
            SourcePackId("sp_20260101000000_pg"),
            "Miles Davis",
            "miles davis",
            "music_artist",
            0.9,
            {"required_entities": ["albums"]},
            [document],
            [snippet],
            {},
            0.9,
            "2026-01-01",
            "1",
        )
        store.record_source_pack(source_pack=source_pack, artifact=artifact)
        graph = KnowledgeGraph()
        graph.add_entity(Entity("miles", str(source_pack.id), "Miles Davis", "person"))
        store.record_graph(graph=graph)
        store.record_model_call(
            ModelCallRecord(
                "mc1",
                "run1",
                "clue_generation",
                "mock-local",
                "baseline-local",
                "p",
                "o",
                1.0,
                10,
                5,
                0.01,
                False,
                0,
                "2026-01-01",
            )
        )
        self.assertTrue(any("source_packs" in sql for sql, _params in connection.executed))
        self.assertTrue(any("graph_entities" in sql for sql, _params in connection.executed))
        self.assertTrue(any("model_calls" in sql for sql, _params in connection.executed))

    def test_signed_manifest_and_s3_health_validation(self) -> None:
        client = FakeS3Client()
        store = S3ArtifactStore(bucket="crosswordai", prefix="prod", client=client)
        artifact = store.write_json({"ok": True}, artifact_id=ArtifactId("art_20260101000000_s3"))
        payload = b'{"ok": true}'
        manifest = signed_export_manifest(artifacts=[artifact], payloads={str(artifact.artifact_id): payload}, secret_key="secret")
        signature = manifest["artifacts"][0]
        from crosswordai.storage import ArtifactSignature

        self.assertTrue(verify_artifact_signature(signature=ArtifactSignature(**signature), payload=payload, secret_key="secret"))
        self.assertTrue(store.health_check().reachable)
        self.assertEqual(client.checked_bucket, "crosswordai")

    def test_otlp_export_trace_correlation_and_dashboard_payloads(self) -> None:
        recorder = TraceRecorder(trace_id="trace_test")
        recorder.record_model_call(
            task_type="qa",
            model_id="mock-local",
            route_id="baseline",
            latency_ms=10.0,
            estimated_cost=0.02,
            cache_hit=True,
        )
        payload = otlp_payload(recorder)
        metrics = dashboard_metrics_payload(recorder, run_id="run1")
        correlation = correlate_trace(
            trace=recorder,
            run_id="run1",
            artifacts=[{"id": "art1"}],
            model_calls=[{"id": "mc1"}],
            source_pack_id="sp1",
        )
        result = OTelTraceExporter(
            OTelExporterConfig("https://otel.example.test/v1/traces"),
            http_post=lambda endpoint, body, headers, timeout: 202,
        ).export(recorder)
        self.assertTrue(result.exported)
        self.assertEqual(correlation.trace_id, "trace_test")
        self.assertEqual(metrics["metrics"]["cache_hit_rate"], 1.0)
        self.assertEqual(payload["resourceSpans"][0]["resource"]["attributes"][0]["key"], "service.name")
        self.assertTrue(default_alert_rules())

    def test_managed_secrets_and_deployment_manifest_validation(self) -> None:
        manifest = DeploymentManifest(
            environment=EnvironmentConfig(
                name="prod",
                database_url="postgresql://db/crosswordai",
                artifact_root="s3://crosswordai-prod",
                allowed_hosts=("api.openai.com",),
                secrets_provider="static-managed",
            ),
            required_secrets=(SecretRef("OPENAI_API_KEY", "static-managed"),),
            backup_policy=BackupPolicy(True, "daily", 30, 90, 14),
            disaster_recovery=DisasterRecoveryPlan(30, 120, "docs/dr.md", ("ops@example.com",), "2026-05-22"),
            egress_urls=("https://api.openai.com/v1/responses",),
            image_ref="ghcr.io/example/crosswordai:prod",
            migration_ref="migrations/0001_core.sql",
            config_checksums={"registries": "sha256:abc"},
        )
        manager = ManagedSecretManager(StaticManagedSecretProvider({"OPENAI_API_KEY": "sk-test-secret"}))
        report = validate_deployment_manifest(manifest, secret_manager=manager)
        self.assertTrue(report.passed)
        self.assertEqual(manager.resolve(manifest.required_secrets)[0].redacted_value, "sk****et")


if __name__ == "__main__":
    unittest.main()
