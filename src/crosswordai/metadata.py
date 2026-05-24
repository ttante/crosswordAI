"""Local metadata persistence for runs and artifacts.

Production will use Postgres. This SQLite implementation gives the platform a
real local development store with the same core concepts: runs and artifacts.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from crosswordai.graph import Entity, KnowledgeGraph, Relationship
from crosswordai.ids import utc_now_iso
from crosswordai.sources import SourcePack
from crosswordai.storage import ArtifactRecord

if TYPE_CHECKING:
    from crosswordai.models import ModelCallRecord


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    run_type: str
    status: str
    created_at: str
    completed_at: str | None = None
    failure_reason: str | None = None


class MetadataStore(Protocol):
    def create_run(self, *, run_id: str, run_type: str, status: str = "running") -> RunRecord:
        ...

    def complete_run(self, *, run_id: str, status: str = "succeeded", failure_reason: str | None = None) -> RunRecord:
        ...

    def get_run(self, run_id: str) -> RunRecord | None:
        ...

    def list_runs(self, *, limit: int = 50) -> list[RunRecord]:
        ...

    def record_artifact(self, *, run_id: str, artifact: ArtifactRecord, content_hash: str | None = None) -> None:
        ...

    def list_artifacts(self, *, run_id: str) -> list[dict[str, Any]]:
        ...

    def record_source_pack(self, *, source_pack: SourcePack, artifact: ArtifactRecord) -> None:
        ...

    def get_source_pack_summary(self, source_pack_id: str) -> dict[str, Any] | None:
        ...

    def get_source_pack_detail(self, source_pack_id: str) -> dict[str, Any] | None:
        ...

    def record_graph(self, *, graph: KnowledgeGraph) -> None:
        ...

    def load_graph(self, source_pack_id: str) -> KnowledgeGraph:
        ...

    def record_model_call(self, record: ModelCallRecord) -> None:
        ...

    def list_model_calls(self, *, run_id: str) -> list[dict[str, Any]]:
        ...


class LocalMetadataStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create_run(self, *, run_id: str, run_type: str, status: str = "running") -> RunRecord:
        record = RunRecord(run_id, run_type, status, utc_now_iso())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, run_type, status, created_at, completed_at, failure_reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.run_type,
                    record.status,
                    record.created_at,
                    record.completed_at,
                    record.failure_reason,
                ),
            )
        return record

    def complete_run(self, *, run_id: str, status: str = "succeeded", failure_reason: str | None = None) -> RunRecord:
        completed_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, completed_at = ?, failure_reason = ?
                WHERE id = ?
                """,
                (status, completed_at, failure_reason, run_id),
            )
        record = self.get_run(run_id)
        if record is None:
            raise KeyError(run_id)
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, run_type, status, created_at, completed_at, failure_reason FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return _run_record(row) if row else None

    def list_runs(self, *, limit: int = 50) -> list[RunRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_type, status, created_at, completed_at, failure_reason
                FROM runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_run_record(row) for row in rows]

    def record_artifact(self, *, run_id: str, artifact: ArtifactRecord, content_hash: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (id, run_id, media_type, object_uri, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(artifact.artifact_id),
                    run_id,
                    artifact.media_type,
                    str(artifact.path),
                    content_hash,
                    artifact.created_at,
                ),
            )

    def list_artifacts(self, *, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, media_type, object_uri, content_hash, created_at
                FROM artifacts
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "run_id": row[1],
                "media_type": row[2],
                "object_uri": row[3],
                "content_hash": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    def record_source_pack(self, *, source_pack: SourcePack, artifact: ArtifactRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_packs (
                    id, theme, normalized_theme, taxonomy, taxonomy_confidence, taxonomy_metadata_json,
                    quality_score, version, created_at, artifact_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_pack.id),
                    source_pack.theme,
                    source_pack.normalized_theme,
                    source_pack.taxonomy,
                    source_pack.taxonomy_confidence,
                    json.dumps(source_pack.taxonomy_metadata),
                    source_pack.quality_score,
                    source_pack.version,
                    source_pack.created_at,
                    str(artifact.artifact_id),
                ),
            )
            for document in source_pack.source_documents:
                conn.execute(
                    """
                    INSERT INTO source_documents (
                        id, source_pack_id, source_type, url_or_path, title, author_or_provider,
                        retrieved_at, license_or_rights_status, trust_score, content_hash, object_storage_uri
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.id,
                        document.source_pack_id,
                        document.source_type,
                        document.url_or_path,
                        document.title,
                        document.author_or_provider,
                        document.retrieved_at,
                        document.license_or_rights_status,
                        document.trust_score,
                        document.content_hash,
                        document.object_storage_uri,
                    ),
                )
            for snippet in source_pack.evidence_snippets:
                conn.execute(
                    """
                    INSERT INTO evidence_snippets (
                        id, source_document_id, snippet_text, start_locator, end_locator,
                        snippet_hash, rights_risk, allowed_use
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snippet.id,
                        snippet.source_document_id,
                        snippet.snippet_text,
                        snippet.start_locator,
                        snippet.end_locator,
                        snippet.snippet_hash,
                        snippet.rights_risk,
                        snippet.allowed_use,
                    ),
                )

    def get_source_pack_summary(self, source_pack_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            source_pack = conn.execute(
                """
                SELECT id, theme, normalized_theme, taxonomy, taxonomy_confidence, taxonomy_metadata_json,
                       quality_score, version, created_at, artifact_id
                FROM source_packs
                WHERE id = ?
                """,
                (source_pack_id,),
            ).fetchone()
            if source_pack is None:
                return None
            document_count = conn.execute(
                "SELECT COUNT(*) FROM source_documents WHERE source_pack_id = ?",
                (source_pack_id,),
            ).fetchone()[0]
            snippet_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM evidence_snippets es
                JOIN source_documents sd ON sd.id = es.source_document_id
                WHERE sd.source_pack_id = ?
                """,
                (source_pack_id,),
            ).fetchone()[0]
        return {
            "id": source_pack[0],
            "theme": source_pack[1],
            "normalized_theme": source_pack[2],
            "taxonomy": source_pack[3],
            "taxonomy_confidence": source_pack[4],
            "taxonomy_metadata": json.loads(source_pack[5]),
            "quality_score": source_pack[6],
            "version": source_pack[7],
            "created_at": source_pack[8],
            "artifact_id": source_pack[9],
            "document_count": document_count,
            "evidence_snippet_count": snippet_count,
        }

    def get_source_pack_detail(self, source_pack_id: str) -> dict[str, Any] | None:
        summary = self.get_source_pack_summary(source_pack_id)
        if summary is None:
            return None
        with self._connect() as conn:
            documents = conn.execute(
                """
                SELECT id, source_type, url_or_path, title, author_or_provider, retrieved_at,
                       license_or_rights_status, trust_score, content_hash, object_storage_uri
                FROM source_documents
                WHERE source_pack_id = ?
                ORDER BY id ASC
                """,
                (source_pack_id,),
            ).fetchall()
            snippets = conn.execute(
                """
                SELECT es.id, es.source_document_id, es.start_locator, es.end_locator,
                       es.snippet_hash, es.rights_risk, es.allowed_use, es.snippet_text
                FROM evidence_snippets es
                JOIN source_documents sd ON sd.id = es.source_document_id
                WHERE sd.source_pack_id = ?
                ORDER BY es.id ASC
                """,
                (source_pack_id,),
            ).fetchall()
            artifact = conn.execute(
                "SELECT object_uri FROM artifacts WHERE id = ?",
                (summary["artifact_id"],),
            ).fetchone()

        rights_metadata: dict[str, Any] = {}
        artifact_uri = artifact[0] if artifact else None
        if artifact_uri:
            artifact_path = Path(artifact_uri)
            if artifact_path.exists():
                payload = json.loads(artifact_path.read_text(encoding="utf-8"))
                rights_metadata = dict(payload.get("rights_metadata", {}))

        return {
            **summary,
            "artifact_uri": artifact_uri,
            "rights_metadata": rights_metadata,
            "source_documents": [
                {
                    "id": row[0],
                    "source_type": row[1],
                    "url_or_path": row[2],
                    "title": row[3],
                    "author_or_provider": row[4],
                    "retrieved_at": row[5],
                    "license_or_rights_status": row[6],
                    "trust_score": row[7],
                    "content_hash": row[8],
                    "object_storage_uri": row[9],
                }
                for row in documents
            ],
            "evidence_snippets": [
                {
                    "id": row[0],
                    "source_document_id": row[1],
                    "start_locator": row[2],
                    "end_locator": row[3],
                    "snippet_hash": row[4],
                    "rights_risk": row[5],
                    "allowed_use": row[6],
                    "snippet_preview": row[7][:120],
                }
                for row in snippets
            ],
        }

    def record_graph(self, *, graph: KnowledgeGraph) -> None:
        with self._connect() as conn:
            for entity in graph.entities.values():
                conn.execute(
                    """
                    INSERT INTO graph_entities (
                        id, source_pack_id, name, entity_type, aliases_json,
                        source_evidence_ids_json, confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_pack_id = excluded.source_pack_id,
                        name = excluded.name,
                        entity_type = excluded.entity_type,
                        aliases_json = excluded.aliases_json,
                        source_evidence_ids_json = excluded.source_evidence_ids_json,
                        confidence = excluded.confidence
                    """,
                    (
                        entity.id,
                        entity.source_pack_id,
                        entity.name,
                        entity.entity_type,
                        json.dumps(list(entity.aliases)),
                        json.dumps(list(entity.source_evidence_ids)),
                        entity.confidence,
                    ),
                )
            for relationship in graph.relationships:
                conn.execute(
                    """
                    INSERT INTO graph_relationships (
                        id, source_pack_id, subject_id, predicate, object_id,
                        source_evidence_ids_json, confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_pack_id = excluded.source_pack_id,
                        subject_id = excluded.subject_id,
                        predicate = excluded.predicate,
                        object_id = excluded.object_id,
                        source_evidence_ids_json = excluded.source_evidence_ids_json,
                        confidence = excluded.confidence
                    """,
                    (
                        relationship.id,
                        relationship.source_pack_id,
                        relationship.subject_id,
                        relationship.predicate,
                        relationship.object_id,
                        json.dumps(list(relationship.source_evidence_ids)),
                        relationship.confidence,
                    ),
                )

    def load_graph(self, source_pack_id: str) -> KnowledgeGraph:
        graph = KnowledgeGraph()
        with self._connect() as conn:
            entity_rows = conn.execute(
                """
                SELECT id, source_pack_id, name, entity_type, aliases_json,
                       source_evidence_ids_json, confidence
                FROM graph_entities
                WHERE source_pack_id = ?
                ORDER BY id ASC
                """,
                (source_pack_id,),
            ).fetchall()
            relationship_rows = conn.execute(
                """
                SELECT id, source_pack_id, subject_id, predicate, object_id,
                       source_evidence_ids_json, confidence
                FROM graph_relationships
                WHERE source_pack_id = ?
                ORDER BY id ASC
                """,
                (source_pack_id,),
            ).fetchall()
        for row in entity_rows:
            graph.add_entity(
                Entity(
                    id=row[0],
                    source_pack_id=row[1],
                    name=row[2],
                    entity_type=row[3],
                    aliases=tuple(json.loads(row[4])),
                    source_evidence_ids=tuple(json.loads(row[5])),
                    confidence=row[6],
                )
            )
        for row in relationship_rows:
            graph.add_relationship(
                Relationship(
                    id=row[0],
                    source_pack_id=row[1],
                    subject_id=row[2],
                    predicate=row[3],
                    object_id=row[4],
                    source_evidence_ids=tuple(json.loads(row[5])),
                    confidence=row[6],
                )
            )
        return graph

    def record_model_call(self, record: ModelCallRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_calls (
                    id, run_id, task_type, model_id, route_id, prompt_hash, output_hash,
                    latency_ms, input_tokens, output_tokens, estimated_cost, cache_hit,
                    retry_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.run_id,
                    record.task_type,
                    record.model_id,
                    record.route_id,
                    record.prompt_hash,
                    record.output_hash,
                    record.latency_ms,
                    record.input_tokens,
                    record.output_tokens,
                    record.estimated_cost,
                    int(record.cache_hit),
                    record.retry_count,
                    record.created_at,
                ),
            )

    def list_model_calls(self, *, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_id, task_type, model_id, route_id, prompt_hash, output_hash,
                       latency_ms, input_tokens, output_tokens, estimated_cost, cache_hit,
                       retry_count, created_at
                FROM model_calls
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "run_id": row[1],
                "task_type": row[2],
                "model_id": row[3],
                "route_id": row[4],
                "prompt_hash": row[5],
                "output_hash": row[6],
                "latency_ms": row[7],
                "input_tokens": row[8],
                "output_tokens": row[9],
                "estimated_cost": row[10],
                "cache_hit": bool(row[11]),
                "retry_count": row[12],
                "created_at": row[13],
            }
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    failure_reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    media_type TEXT NOT NULL,
                    object_uri TEXT NOT NULL,
                    content_hash TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_packs (
                    id TEXT PRIMARY KEY,
                    theme TEXT NOT NULL,
                    normalized_theme TEXT NOT NULL,
                    taxonomy TEXT NOT NULL,
                    taxonomy_confidence REAL NOT NULL DEFAULT 0,
                    taxonomy_metadata_json TEXT NOT NULL DEFAULT '{}',
                    quality_score REAL NOT NULL,
                    version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_documents (
                    id TEXT PRIMARY KEY,
                    source_pack_id TEXT NOT NULL REFERENCES source_packs(id),
                    source_type TEXT NOT NULL,
                    url_or_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author_or_provider TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    license_or_rights_status TEXT NOT NULL,
                    trust_score REAL NOT NULL,
                    content_hash TEXT NOT NULL,
                    object_storage_uri TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_snippets (
                    id TEXT PRIMARY KEY,
                    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
                    snippet_text TEXT NOT NULL,
                    start_locator INTEGER NOT NULL,
                    end_locator INTEGER NOT NULL,
                    snippet_hash TEXT NOT NULL,
                    rights_risk TEXT NOT NULL,
                    allowed_use TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_entities (
                    id TEXT PRIMARY KEY,
                    source_pack_id TEXT NOT NULL REFERENCES source_packs(id),
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    source_evidence_ids_json TEXT NOT NULL,
                    confidence REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_relationships (
                    id TEXT PRIMARY KEY,
                    source_pack_id TEXT NOT NULL REFERENCES source_packs(id),
                    subject_id TEXT NOT NULL REFERENCES graph_entities(id),
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL REFERENCES graph_entities(id),
                    source_evidence_ids_json TEXT NOT NULL,
                    confidence REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_calls (
                    id TEXT PRIMARY KEY,
                    run_id TEXT REFERENCES runs(id),
                    task_type TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    route_id TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    output_hash TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    estimated_cost REAL NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


class PostgresMetadataStore:
    """Postgres-backed metadata store.

    The adapter is intentionally isolated behind an optional dependency so local
    development and tests do not require a running database. Install a psycopg 3
    compatible driver and provide a Postgres URL to activate this implementation.
    """

    def __init__(self, database_url: str, *, psycopg_module: Any | None = None) -> None:
        if psycopg_module is None:
            try:
                import psycopg  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "Postgres metadata store requires the optional 'psycopg' package. "
                    "Install psycopg and ensure pgvector is available in the target database."
                ) from exc
            psycopg_module = psycopg
        self.database_url = database_url
        self._psycopg = psycopg_module

    def execute_script(self, sql: str) -> None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)

    def create_run(self, *, run_id: str, run_type: str, status: str = "running") -> RunRecord:
        record = RunRecord(run_id, run_type, status, utc_now_iso())
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO runs (id, run_type, status, created_at, completed_at, failure_reason)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.id,
                        record.run_type,
                        record.status,
                        record.created_at,
                        record.completed_at,
                        record.failure_reason,
                    ),
                )
        return record

    def complete_run(self, *, run_id: str, status: str = "succeeded", failure_reason: str | None = None) -> RunRecord:
        completed_at = utc_now_iso()
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE runs
                    SET status = %s, completed_at = %s, failure_reason = %s
                    WHERE id = %s
                    """,
                    (status, completed_at, failure_reason, run_id),
                )
        record = self.get_run(run_id)
        if record is None:
            raise KeyError(run_id)
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, run_type, status, created_at, completed_at, failure_reason FROM runs WHERE id = %s",
                    (run_id,),
                )
                row = cursor.fetchone()
        return _run_record(row) if row else None

    def list_runs(self, *, limit: int = 50) -> list[RunRecord]:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, run_type, status, created_at, completed_at, failure_reason
                    FROM runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
        return [_run_record(row) for row in rows]

    def record_artifact(self, *, run_id: str, artifact: ArtifactRecord, content_hash: str | None = None) -> None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO artifacts (id, run_id, media_type, object_uri, content_hash, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (str(artifact.artifact_id), run_id, artifact.media_type, str(artifact.path), content_hash, artifact.created_at),
                )

    def list_artifacts(self, *, run_id: str) -> list[dict[str, Any]]:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, run_id, media_type, object_uri, content_hash, created_at
                    FROM artifacts
                    WHERE run_id = %s
                    ORDER BY created_at ASC
                    """,
                    (run_id,),
                )
                rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "run_id": row[1],
                "media_type": row[2],
                "object_uri": row[3],
                "content_hash": row[4],
                "created_at": str(row[5]),
            }
            for row in rows
        ]

    def record_source_pack(self, *, source_pack: SourcePack, artifact: ArtifactRecord) -> None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_packs (
                        id, theme, normalized_theme, taxonomy, taxonomy_confidence, taxonomy_metadata_json,
                        quality_score, version, created_at, artifact_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        theme = excluded.theme,
                        normalized_theme = excluded.normalized_theme,
                        taxonomy = excluded.taxonomy,
                        taxonomy_confidence = excluded.taxonomy_confidence,
                        taxonomy_metadata_json = excluded.taxonomy_metadata_json,
                        quality_score = excluded.quality_score,
                        version = excluded.version,
                        created_at = excluded.created_at,
                        artifact_id = excluded.artifact_id
                    """,
                    (
                        str(source_pack.id),
                        source_pack.theme,
                        source_pack.normalized_theme,
                        source_pack.taxonomy,
                        source_pack.taxonomy_confidence,
                        json.dumps(source_pack.taxonomy_metadata),
                        source_pack.quality_score,
                        source_pack.version,
                        source_pack.created_at,
                        str(artifact.artifact_id),
                    ),
                )
                for document in source_pack.source_documents:
                    cursor.execute(
                        """
                        INSERT INTO source_documents (
                            id, source_pack_id, source_type, url_or_path, title, author_or_provider,
                            retrieved_at, license_or_rights_status, trust_score, content_hash, object_storage_uri
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(id) DO UPDATE SET
                            source_pack_id = excluded.source_pack_id,
                            source_type = excluded.source_type,
                            url_or_path = excluded.url_or_path,
                            title = excluded.title,
                            author_or_provider = excluded.author_or_provider,
                            retrieved_at = excluded.retrieved_at,
                            license_or_rights_status = excluded.license_or_rights_status,
                            trust_score = excluded.trust_score,
                            content_hash = excluded.content_hash,
                            object_storage_uri = excluded.object_storage_uri
                        """,
                        (
                            document.id,
                            document.source_pack_id,
                            document.source_type,
                            document.url_or_path,
                            document.title,
                            document.author_or_provider,
                            document.retrieved_at,
                            document.license_or_rights_status,
                            document.trust_score,
                            document.content_hash,
                            document.object_storage_uri,
                        ),
                    )
                for snippet in source_pack.evidence_snippets:
                    cursor.execute(
                        """
                        INSERT INTO evidence_snippets (
                            id, source_document_id, snippet_text, start_locator, end_locator,
                            snippet_hash, rights_risk, allowed_use
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(id) DO UPDATE SET
                            source_document_id = excluded.source_document_id,
                            snippet_text = excluded.snippet_text,
                            start_locator = excluded.start_locator,
                            end_locator = excluded.end_locator,
                            snippet_hash = excluded.snippet_hash,
                            rights_risk = excluded.rights_risk,
                            allowed_use = excluded.allowed_use
                        """,
                        (
                            snippet.id,
                            snippet.source_document_id,
                            snippet.snippet_text,
                            snippet.start_locator,
                            snippet.end_locator,
                            snippet.snippet_hash,
                            snippet.rights_risk,
                            snippet.allowed_use,
                        ),
                    )

    def get_source_pack_summary(self, source_pack_id: str) -> dict[str, Any] | None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, theme, normalized_theme, taxonomy, taxonomy_confidence, taxonomy_metadata_json,
                           quality_score, version, created_at, artifact_id
                    FROM source_packs
                    WHERE id = %s
                    """,
                    (source_pack_id,),
                )
                source_pack = cursor.fetchone()
                if source_pack is None:
                    return None
                cursor.execute("SELECT COUNT(*) FROM source_documents WHERE source_pack_id = %s", (source_pack_id,))
                document_count = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM evidence_snippets es
                    JOIN source_documents sd ON sd.id = es.source_document_id
                    WHERE sd.source_pack_id = %s
                    """,
                    (source_pack_id,),
                )
                snippet_count = cursor.fetchone()[0]
        return {
            "id": source_pack[0],
            "theme": source_pack[1],
            "normalized_theme": source_pack[2],
            "taxonomy": source_pack[3],
            "taxonomy_confidence": source_pack[4],
            "taxonomy_metadata": _loads_json(source_pack[5]),
            "quality_score": source_pack[6],
            "version": source_pack[7],
            "created_at": str(source_pack[8]),
            "artifact_id": source_pack[9],
            "document_count": document_count,
            "evidence_snippet_count": snippet_count,
        }

    def get_source_pack_detail(self, source_pack_id: str) -> dict[str, Any] | None:
        summary = self.get_source_pack_summary(source_pack_id)
        if summary is None:
            return None
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_type, url_or_path, title, author_or_provider, retrieved_at,
                           license_or_rights_status, trust_score, content_hash, object_storage_uri
                    FROM source_documents
                    WHERE source_pack_id = %s
                    ORDER BY id ASC
                    """,
                    (source_pack_id,),
                )
                documents = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT es.id, es.source_document_id, es.start_locator, es.end_locator,
                           es.snippet_hash, es.rights_risk, es.allowed_use, es.snippet_text
                    FROM evidence_snippets es
                    JOIN source_documents sd ON sd.id = es.source_document_id
                    WHERE sd.source_pack_id = %s
                    ORDER BY es.id ASC
                    """,
                    (source_pack_id,),
                )
                snippets = cursor.fetchall()
                cursor.execute("SELECT object_uri FROM artifacts WHERE id = %s", (summary["artifact_id"],))
                artifact = cursor.fetchone()
        return {
            **summary,
            "artifact_uri": artifact[0] if artifact else None,
            "rights_metadata": {},
            "source_documents": [
                {
                    "id": row[0],
                    "source_type": row[1],
                    "url_or_path": row[2],
                    "title": row[3],
                    "author_or_provider": row[4],
                    "retrieved_at": str(row[5]),
                    "license_or_rights_status": row[6],
                    "trust_score": row[7],
                    "content_hash": row[8],
                    "object_storage_uri": row[9],
                }
                for row in documents
            ],
            "evidence_snippets": [
                {
                    "id": row[0],
                    "source_document_id": row[1],
                    "start_locator": row[2],
                    "end_locator": row[3],
                    "snippet_hash": row[4],
                    "rights_risk": row[5],
                    "allowed_use": row[6],
                    "snippet_preview": row[7][:120],
                }
                for row in snippets
            ],
        }

    def record_graph(self, *, graph: KnowledgeGraph) -> None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                for entity in graph.entities.values():
                    cursor.execute(
                        """
                        INSERT INTO graph_entities (
                            id, source_pack_id, name, entity_type, aliases_json,
                            source_evidence_ids_json, confidence
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(id) DO UPDATE SET
                            source_pack_id = excluded.source_pack_id,
                            name = excluded.name,
                            entity_type = excluded.entity_type,
                            aliases_json = excluded.aliases_json,
                            source_evidence_ids_json = excluded.source_evidence_ids_json,
                            confidence = excluded.confidence
                        """,
                        (
                            entity.id,
                            entity.source_pack_id,
                            entity.name,
                            entity.entity_type,
                            json.dumps(list(entity.aliases)),
                            json.dumps(list(entity.source_evidence_ids)),
                            entity.confidence,
                        ),
                    )
                for relationship in graph.relationships:
                    cursor.execute(
                        """
                        INSERT INTO graph_relationships (
                            id, source_pack_id, subject_id, predicate, object_id,
                            source_evidence_ids_json, confidence
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(id) DO UPDATE SET
                            source_pack_id = excluded.source_pack_id,
                            subject_id = excluded.subject_id,
                            predicate = excluded.predicate,
                            object_id = excluded.object_id,
                            source_evidence_ids_json = excluded.source_evidence_ids_json,
                            confidence = excluded.confidence
                        """,
                        (
                            relationship.id,
                            relationship.source_pack_id,
                            relationship.subject_id,
                            relationship.predicate,
                            relationship.object_id,
                            json.dumps(list(relationship.source_evidence_ids)),
                            relationship.confidence,
                        ),
                    )

    def load_graph(self, source_pack_id: str) -> KnowledgeGraph:
        graph = KnowledgeGraph()
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_pack_id, name, entity_type, aliases_json,
                           source_evidence_ids_json, confidence
                    FROM graph_entities
                    WHERE source_pack_id = %s
                    ORDER BY id ASC
                    """,
                    (source_pack_id,),
                )
                entity_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT id, source_pack_id, subject_id, predicate, object_id,
                           source_evidence_ids_json, confidence
                    FROM graph_relationships
                    WHERE source_pack_id = %s
                    ORDER BY id ASC
                    """,
                    (source_pack_id,),
                )
                relationship_rows = cursor.fetchall()
        for row in entity_rows:
            graph.add_entity(
                Entity(
                    id=row[0],
                    source_pack_id=row[1],
                    name=row[2],
                    entity_type=row[3],
                    aliases=tuple(_loads_json(row[4])),
                    source_evidence_ids=tuple(_loads_json(row[5])),
                    confidence=row[6],
                )
            )
        for row in relationship_rows:
            graph.add_relationship(
                Relationship(
                    id=row[0],
                    source_pack_id=row[1],
                    subject_id=row[2],
                    predicate=row[3],
                    object_id=row[4],
                    source_evidence_ids=tuple(_loads_json(row[5])),
                    confidence=row[6],
                )
            )
        return graph

    def record_model_call(self, record: ModelCallRecord) -> None:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO model_calls (
                        id, run_id, task_type, model_id, route_id, prompt_hash, output_hash,
                        latency_ms, input_tokens, output_tokens, estimated_cost, cache_hit,
                        retry_count, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        run_id = excluded.run_id,
                        task_type = excluded.task_type,
                        model_id = excluded.model_id,
                        route_id = excluded.route_id,
                        prompt_hash = excluded.prompt_hash,
                        output_hash = excluded.output_hash,
                        latency_ms = excluded.latency_ms,
                        input_tokens = excluded.input_tokens,
                        output_tokens = excluded.output_tokens,
                        estimated_cost = excluded.estimated_cost,
                        cache_hit = excluded.cache_hit,
                        retry_count = excluded.retry_count,
                        created_at = excluded.created_at
                    """,
                    (
                        record.id,
                        record.run_id,
                        record.task_type,
                        record.model_id,
                        record.route_id,
                        record.prompt_hash,
                        record.output_hash,
                        record.latency_ms,
                        record.input_tokens,
                        record.output_tokens,
                        record.estimated_cost,
                        int(record.cache_hit),
                        record.retry_count,
                        record.created_at,
                    ),
                )

    def list_model_calls(self, *, run_id: str) -> list[dict[str, Any]]:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, run_id, task_type, model_id, route_id, prompt_hash, output_hash,
                           latency_ms, input_tokens, output_tokens, estimated_cost, cache_hit,
                           retry_count, created_at
                    FROM model_calls
                    WHERE run_id = %s
                    ORDER BY created_at ASC
                    """,
                    (run_id,),
                )
                rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "run_id": row[1],
                "task_type": row[2],
                "model_id": row[3],
                "route_id": row[4],
                "prompt_hash": row[5],
                "output_hash": row[6],
                "latency_ms": row[7],
                "input_tokens": row[8],
                "output_tokens": row[9],
                "estimated_cost": row[10],
                "cache_hit": bool(row[11]),
                "retry_count": row[12],
                "created_at": str(row[13]),
            }
            for row in rows
        ]

    def health_check(self) -> dict[str, Any]:
        with self._psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
        return {"database": "postgres", "reachable": row == (1,) or row == [1]}


def _run_record(row: sqlite3.Row | tuple[Any, ...]) -> RunRecord:
    return RunRecord(
        id=row[0],
        run_type=row[1],
        status=row[2],
        created_at=row[3],
        completed_at=row[4],
        failure_reason=row[5],
    )


def _loads_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def metadata_store_from_settings(settings: Any) -> MetadataStore:
    database_url = getattr(settings, "database_url", None)
    if database_url:
        database_url = str(database_url)
        if database_url.startswith(("postgres://", "postgresql://")):
            return PostgresMetadataStore(database_url)
        raise RuntimeError(f"unsupported database_url: {database_url}")
    return LocalMetadataStore(settings.metadata_db)
