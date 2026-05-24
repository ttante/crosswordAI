"""Source-pack primitives and user-note ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from crosswordai.connectors import ConnectorResult, SourceConnector
from crosswordai.ids import SourcePackId, new_source_pack_id, utc_now_iso
from crosswordai.safety import BaselineSafetyScanner, PolicyResult
from crosswordai.storage import LocalArtifactStore
from crosswordai.taxonomy import RuleBasedTaxonomyClassifier, TaxonomyResult


@dataclass(frozen=True, slots=True)
class SourceDocument:
    id: str
    source_pack_id: str
    source_type: str
    url_or_path: str
    title: str
    author_or_provider: str
    retrieved_at: str
    license_or_rights_status: str
    trust_score: float
    content_hash: str
    object_storage_uri: str


@dataclass(frozen=True, slots=True)
class EvidenceSnippet:
    id: str
    source_document_id: str
    snippet_text: str
    start_locator: int
    end_locator: int
    snippet_hash: str
    rights_risk: str
    allowed_use: str
    derived_entities: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SourcePack:
    id: SourcePackId
    theme: str
    normalized_theme: str
    taxonomy: str
    taxonomy_confidence: float
    taxonomy_metadata: dict[str, Any]
    source_documents: list[SourceDocument]
    evidence_snippets: list[EvidenceSnippet]
    rights_metadata: dict[str, Any]
    quality_score: float
    created_at: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = str(self.id)
        return payload


class UserNotesSourcePackBuilder:
    def __init__(
        self,
        artifact_store: LocalArtifactStore,
        scanner: BaselineSafetyScanner | None = None,
        taxonomy_classifier: RuleBasedTaxonomyClassifier | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.scanner = scanner or BaselineSafetyScanner()
        self.taxonomy_classifier = taxonomy_classifier or RuleBasedTaxonomyClassifier()

    def build(self, *, theme: str, notes_path: Path) -> tuple[SourcePack, PolicyResult]:
        text = notes_path.read_text(encoding="utf-8")
        policy = self.scanner.scan(text)
        taxonomy = self.taxonomy_classifier.classify(theme, text)
        source_pack_id = new_source_pack_id()
        artifact = self.artifact_store.write_bytes(
            text.encode("utf-8"),
            extension=".txt",
            media_type="text/plain",
        )
        document = SourceDocument(
            id=f"doc_{_short_hash(str(notes_path))}",
            source_pack_id=str(source_pack_id),
            source_type="user_notes",
            url_or_path=str(notes_path),
            title=notes_path.name,
            author_or_provider="user",
            retrieved_at=utc_now_iso(),
            license_or_rights_status="user_provided",
            trust_score=0.95,
            content_hash=_sha256(text),
            object_storage_uri=str(artifact.path),
        )
        snippets = _make_snippets(document.id, text)
        quality_score = 0.0 if not policy.passed else min(1.0, 0.45 + len(snippets) * 0.05)
        source_pack = SourcePack(
            id=source_pack_id,
            theme=theme,
            normalized_theme=theme.strip().lower(),
            taxonomy=taxonomy.taxonomy,
            taxonomy_confidence=taxonomy.confidence,
            taxonomy_metadata=_taxonomy_metadata(taxonomy),
            source_documents=[document],
            evidence_snippets=snippets,
            rights_metadata={
                "policy_status": policy.status,
                "findings": [asdict(finding) for finding in policy.findings],
            },
            quality_score=quality_score,
            created_at=utc_now_iso(),
            version="1",
        )
        return source_pack, policy


class MultiSourcePackBuilder:
    def __init__(
        self,
        artifact_store: LocalArtifactStore,
        connectors: dict[str, SourceConnector],
        scanner: BaselineSafetyScanner | None = None,
        taxonomy_classifier: RuleBasedTaxonomyClassifier | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.connectors = connectors
        self.scanner = scanner or BaselineSafetyScanner()
        self.taxonomy_classifier = taxonomy_classifier or RuleBasedTaxonomyClassifier()

    def build(
        self,
        *,
        theme: str,
        notes_path: Path | None = None,
        source_names: list[str] | None = None,
    ) -> tuple[SourcePack, PolicyResult]:
        source_pack_id = new_source_pack_id()
        documents: list[SourceDocument] = []
        snippets: list[EvidenceSnippet] = []
        findings: list[dict[str, Any]] = []
        taxonomy_text_parts: list[str] = []

        if notes_path is not None:
            text = notes_path.read_text(encoding="utf-8")
            policy = self.scanner.scan(text)
            findings.extend(asdict(finding) for finding in policy.findings)
            document = self._document_from_user_notes(source_pack_id, notes_path, text)
            documents.append(document)
            snippets.extend(_make_snippets(document.id, text))
            taxonomy_text_parts.append(text)

        for source_name in source_names or []:
            connector = self.connectors[source_name]
            result = connector.fetch(theme)
            policy = self.scanner.scan(result.content)
            findings.extend(asdict(finding) | {"source_type": result.source_type} for finding in policy.findings)
            document = self._document_from_connector_result(source_pack_id, result)
            documents.append(document)
            snippets.extend(_make_snippets(document.id, result.content))
            taxonomy_text_parts.append(result.content)

        combined_text = "\n\n".join(taxonomy_text_parts)
        taxonomy = self.taxonomy_classifier.classify(theme, combined_text)
        policy_status = "quarantined" if any(finding.get("severity") == "high" for finding in findings) else "passed"
        quality_score = 0.0 if policy_status != "passed" else min(1.0, 0.4 + len(documents) * 0.1 + len(snippets) * 0.03)
        source_pack = SourcePack(
            id=source_pack_id,
            theme=theme,
            normalized_theme=theme.strip().lower(),
            taxonomy=taxonomy.taxonomy,
            taxonomy_confidence=taxonomy.confidence,
            taxonomy_metadata=_taxonomy_metadata(taxonomy),
            source_documents=documents,
            evidence_snippets=snippets,
            rights_metadata={
                "policy_status": policy_status,
                "findings": findings,
            },
            quality_score=quality_score,
            created_at=utc_now_iso(),
            version="1",
        )
        return source_pack, PolicyResult(policy_status, [])

    def _document_from_user_notes(self, source_pack_id: SourcePackId, notes_path: Path, text: str) -> SourceDocument:
        artifact = self.artifact_store.write_bytes(
            text.encode("utf-8"),
            extension=".txt",
            media_type="text/plain",
        )
        return SourceDocument(
            id=f"doc_{_short_hash(str(notes_path))}",
            source_pack_id=str(source_pack_id),
            source_type="user_notes",
            url_or_path=str(notes_path),
            title=notes_path.name,
            author_or_provider="user",
            retrieved_at=utc_now_iso(),
            license_or_rights_status="user_provided",
            trust_score=0.95,
            content_hash=_sha256(text),
            object_storage_uri=str(artifact.path),
        )

    def _document_from_connector_result(self, source_pack_id: SourcePackId, result: ConnectorResult) -> SourceDocument:
        artifact = self.artifact_store.write_json(
            {
                "source_type": result.source_type,
                "title": result.title,
                "url_or_path": result.url_or_path,
                "provider": result.provider,
                "license_or_rights_status": result.license_or_rights_status,
                "content": result.content,
                "raw_metadata": result.raw_metadata or {},
            },
            media_type="application/vnd.crosswordai.source-snapshot+json",
        )
        return SourceDocument(
            id=f"doc_{_short_hash(result.provider + result.url_or_path + result.title)}",
            source_pack_id=str(source_pack_id),
            source_type=result.source_type,
            url_or_path=result.url_or_path,
            title=result.title,
            author_or_provider=result.provider,
            retrieved_at=utc_now_iso(),
            license_or_rights_status=result.license_or_rights_status,
            trust_score=result.trust_score,
            content_hash=_sha256(result.content),
            object_storage_uri=str(artifact.path),
        )


def _taxonomy_metadata(taxonomy: TaxonomyResult) -> dict[str, Any]:
    return {
        "version": taxonomy.version,
        "required_entities": list(taxonomy.required_entities),
        "preferred_sources": list(taxonomy.preferred_sources),
        "rights_threshold": taxonomy.rights_threshold,
        "retrieval_policy": taxonomy.retrieval_policy or {},
    }


def _make_snippets(source_document_id: str, text: str) -> list[EvidenceSnippet]:
    snippets: list[EvidenceSnippet] = []
    offset = 0
    for paragraph in [part.strip() for part in text.split("\n\n") if part.strip()]:
        end = offset + len(paragraph)
        snippet_text = paragraph[:500]
        snippets.append(
            EvidenceSnippet(
                id=f"ev_{_short_hash(source_document_id + str(offset) + snippet_text)}",
                source_document_id=source_document_id,
                snippet_text=snippet_text,
                start_locator=offset,
                end_locator=end,
                snippet_hash=_sha256(snippet_text),
                rights_risk="low" if len(snippet_text) < 280 else "medium",
                allowed_use="internal_evidence",
            )
        )
        offset = end + 2
    return snippets


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _short_hash(text: str) -> str:
    return _sha256(text)[:12]
