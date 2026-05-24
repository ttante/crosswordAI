"""Stable response contracts for the local web API and React client."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from crosswordai import __version__


JsonObject = dict[str, Any]
StageStatus = Literal["pending", "running", "succeeded", "failed", "quarantined", "skipped"]
RunStatus = Literal["running", "succeeded", "failed", "quarantined"]
Direction = Literal["across", "down"]


@dataclass(frozen=True, slots=True)
class ApiError:
    code: str
    message: str
    details: JsonObject = field(default_factory=dict)
    remediation: str | None = None

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ErrorResponse:
    error: ApiError
    correlation_id: str

    def to_dict(self) -> JsonObject:
        return {"error": self.error.to_dict(), "correlation_id": self.correlation_id}


@dataclass(frozen=True, slots=True)
class HealthResponse:
    service: Literal["crosswordai-web"]
    version: str
    status: Literal["ok", "degraded"]
    correlation_id: str
    dependencies: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return asdict(self)


def health_response(*, correlation_id: str, dependencies: JsonObject | None = None) -> HealthResponse:
    return HealthResponse(
        service="crosswordai-web",
        version=__version__,
        status="ok",
        correlation_id=correlation_id,
        dependencies=dependencies or {},
    )


def error_response(
    *,
    code: str,
    message: str,
    correlation_id: str,
    details: JsonObject | None = None,
    remediation: str | None = None,
) -> ErrorResponse:
    return ErrorResponse(
        error=ApiError(code=code, message=message, details=details or {}, remediation=remediation),
        correlation_id=correlation_id,
    )


@dataclass(frozen=True, slots=True)
class ArtifactSummary:
    artifact_id: str
    label: str
    media_type: str
    created_at: str
    href: str | None = None
    checksum: str | None = None

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    run_type: str
    status: RunStatus
    theme: str
    created_at: str
    completed_at: str | None = None
    source_pack_id: str | None = None
    puzzle_id: str | None = None
    artifact_count: int = 0

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunStage:
    stage_id: str
    label: str
    status: StageStatus
    started_at: str | None = None
    completed_at: str | None = None
    failures: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunDetailResponse:
    run: RunSummary
    stages: tuple[RunStage, ...]
    artifacts: tuple[ArtifactSummary, ...]
    qa_summary: JsonObject
    links: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunListResponse:
    runs: tuple[RunSummary, ...]

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourcePackResponse:
    source_pack_id: str
    theme: str
    taxonomy: str
    taxonomy_confidence: float
    quality_score: float
    document_count: int
    evidence_snippet_count: int
    rights_status: str
    evidence_previews: tuple[JsonObject, ...] = ()
    vector_notes: JsonObject = field(default_factory=dict)
    graph_summary: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SourcePackBuildResponse:
    run: RunSummary
    source_pack: SourcePackResponse
    artifact: ArtifactSummary

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlayerGrid:
    width: int
    height: int
    rows: tuple[str, ...]

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlayerClue:
    clue_id: str
    number: int
    direction: Direction
    row: int
    col: int
    answer_length: int
    clue_text: str
    difficulty: str
    answer_hash: str
    source_evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlayerPuzzleResponse:
    puzzle_id: str
    title: str
    theme: str
    status: Literal["playable", "quarantined"]
    grid: PlayerGrid
    clues: tuple[PlayerClue, ...]
    metadata: JsonObject
    export_policy: JsonObject

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RegistryIndexResponse:
    registries: dict[str, dict[str, str]]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BatchSummaryResponse:
    batch_id: str
    status: StageStatus
    created_at: str
    routes: tuple[str, ...]
    theme_count: int
    summary: JsonObject
    artifacts: tuple[ArtifactSummary, ...] = ()

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReportSummaryResponse:
    run_id: str
    puzzle_id: str
    source_coverage: JsonObject
    model_contribution: JsonObject
    qa_scorecard: JsonObject
    links: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return asdict(self)
