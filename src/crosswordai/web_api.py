"""FastAPI wrapper for the local CrosswordAI platform.

The web API intentionally stays thin: it exposes stable HTTP contracts while the
generation, storage, metadata, and governance logic remains in domain modules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised when optional web dependencies are installed.
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException
except ModuleNotFoundError:  # pragma: no cover - local core tests do not require FastAPI.
    FastAPI = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]
    JSONResponse = None  # type: ignore[assignment]
    StarletteHTTPException = Exception  # type: ignore[assignment]

from crosswordai.config import Settings
from crosswordai.core_path import CorePathRequest, HardenedCorePathPipeline
from crosswordai.ids import ArtifactId, new_run_id
from crosswordai.metadata import MetadataStore, RunRecord, metadata_store_from_settings
from crosswordai.sources import UserNotesSourcePackBuilder
from crosswordai.storage import ArtifactRecord, LocalArtifactStore
from crosswordai.web_contracts import (
    ArtifactSummary,
    PlayerClue,
    PlayerGrid,
    PlayerPuzzleResponse,
    RunDetailResponse,
    RunListResponse,
    RunStage,
    RunSummary,
    SourcePackBuildResponse,
    SourcePackResponse,
    error_response,
    health_response,
)


CORRELATION_ID_HEADER = "x-correlation-id"


class WebApiDependencyError(RuntimeError):
    """Raised when the optional web API dependencies are not installed."""


class ApiHTTPError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.remediation = remediation


@dataclass(frozen=True, slots=True)
class WebApiServices:
    settings: Settings
    artifact_store: LocalArtifactStore
    metadata_store: MetadataStore


def create_app(*, settings: Settings | None = None) -> Any:
    if FastAPI is None or JSONResponse is None:
        raise WebApiDependencyError(
            "FastAPI web dependencies are not installed. Install the project with web dependencies first."
        )

    resolved_settings = settings or Settings.load()
    resolved_settings.ensure_dirs()
    artifact_store = LocalArtifactStore(resolved_settings.artifact_root)
    metadata_store = metadata_store_from_settings(resolved_settings)
    app = FastAPI(title="CrosswordAI Web API", version="0.1.0")
    app.state.services = WebApiServices(
        settings=resolved_settings,
        artifact_store=artifact_store,
        metadata_store=metadata_store,
    )

    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next: Any) -> Any:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or _new_correlation_id()
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response

    @app.exception_handler(ApiHTTPError)
    async def api_http_error_handler(request: Request, exc: ApiHTTPError) -> JSONResponse:
        return _json_error(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request=request,
            details=exc.details,
            remediation=exc.remediation,
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status_code = int(getattr(exc, "status_code", 500))
        code = "not_found" if status_code == 404 else "http_error"
        return _json_error(
            status_code=status_code,
            code=code,
            message=str(getattr(exc, "detail", "HTTP error")),
            request=request,
            remediation="Check the endpoint path and HTTP method." if status_code == 404 else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return _json_error(
            status_code=500,
            code="internal_error",
            message="Unexpected server error.",
            request=request,
            details={"type": type(exc).__name__},
            remediation="Check server logs with the returned correlation ID.",
        )

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        dependencies = {
            "artifact_root": str(resolved_settings.artifact_root),
            "metadata_db": str(resolved_settings.metadata_db),
            "registry_root": str(resolved_settings.registry_root),
        }
        return health_response(correlation_id=_correlation_id(request), dependencies=dependencies).to_dict()

    @app.post("/api/source-packs", status_code=201)
    async def create_source_pack(request: Request) -> dict[str, Any]:
        services = _services(request)
        payload = await _json_payload(request)
        theme = _required_text(payload, "theme")
        notes_text = _required_text(payload, "notes")
        notes_path = _write_notes_file(services.settings, theme=theme, notes=notes_text)

        run_id = str(new_run_id())
        services.metadata_store.create_run(run_id=run_id, run_type="source_pack_build")
        source_pack, policy = UserNotesSourcePackBuilder(services.artifact_store).build(
            theme=theme,
            notes_path=notes_path,
        )
        artifact = services.artifact_store.write_json(
            source_pack.to_dict(),
            media_type="application/vnd.crosswordai.source-pack+json",
        )
        services.metadata_store.record_artifact(run_id=run_id, artifact=artifact)
        services.metadata_store.record_source_pack(source_pack=source_pack, artifact=artifact)
        run = services.metadata_store.complete_run(
            run_id=run_id,
            status="succeeded" if policy.passed else "quarantined",
            failure_reason=None if policy.passed else policy.status,
        )
        source_pack_response = _source_pack_response_from_detail(
            services.metadata_store.get_source_pack_detail(str(source_pack.id))
        )
        return SourcePackBuildResponse(
            run=_run_summary(run, artifact_count=1, theme=theme, source_pack_id=str(source_pack.id)),
            source_pack=source_pack_response,
            artifact=_artifact_summary(artifact),
        ).to_dict()

    @app.get("/api/source-packs/{source_pack_id}")
    async def get_source_pack(source_pack_id: str, request: Request) -> dict[str, Any]:
        detail = _services(request).metadata_store.get_source_pack_detail(source_pack_id)
        if detail is None:
            raise ApiHTTPError(
                status_code=404,
                code="source_pack_not_found",
                message="Source pack was not found.",
                details={"source_pack_id": source_pack_id},
                remediation="Check the source pack ID from the run detail response.",
            )
        return _source_pack_response_from_detail(detail).to_dict()

    @app.post("/api/puzzles/generate", status_code=201)
    async def generate_puzzle(request: Request) -> dict[str, Any]:
        services = _services(request)
        payload = await _json_payload(request)
        theme = _required_text(payload, "theme")
        notes_text = _required_text(payload, "notes")
        route_id = str(payload.get("route_id") or "baseline-local")
        puzzle_id = str(payload.get("puzzle_id") or f"puzzle_{uuid.uuid4().hex[:10]}")
        grid_size = _int_body(payload, "grid_size", default=5, minimum=3, maximum=21)
        candidate_limit = _int_body(payload, "candidate_limit", default=25, minimum=1, maximum=200)
        clue_styles = _string_list_body(payload, "clue_styles", default=("direct",))
        notes_path = _write_notes_file(services.settings, theme=theme, notes=notes_text)

        result = HardenedCorePathPipeline(
            artifact_store=services.artifact_store,
            metadata_store=services.metadata_store,
        ).run(
            CorePathRequest(
                theme=theme,
                notes_path=notes_path,
                route_id=route_id,
                puzzle_id=puzzle_id,
                grid_size=grid_size,
                clue_styles=clue_styles,
                candidate_limit=candidate_limit,
            )
        )
        detail = _run_detail_response(
            services.metadata_store,
            services.artifact_store,
            result.run_id,
            fallback_theme=theme,
            fallback_source_pack_id=result.source_pack_id,
            fallback_puzzle_id=result.puzzle_id,
        )
        return detail.to_dict()

    @app.get("/api/runs")
    async def list_runs(request: Request) -> dict[str, Any]:
        services = _services(request)
        limit = _int_query(request, "limit", default=25, minimum=1, maximum=100)
        summaries = []
        for run in services.metadata_store.list_runs(limit=limit):
            artifacts = services.metadata_store.list_artifacts(run_id=run.id)
            context = _run_context_from_artifacts(services.artifact_store, artifacts)
            summaries.append(
                _run_summary(
                    run,
                    artifact_count=len(artifacts),
                    theme=context.get("theme"),
                    source_pack_id=context.get("source_pack_id"),
                    puzzle_id=context.get("puzzle_id"),
                )
            )
        return RunListResponse(runs=tuple(summaries)).to_dict()

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        services = _services(request)
        return _run_detail_response(services.metadata_store, services.artifact_store, run_id).to_dict()

    @app.get("/api/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str, request: Request) -> dict[str, Any]:
        services = _services(request)
        try:
            return services.artifact_store.read_json(ArtifactId(artifact_id))
        except (FileNotFoundError, ValueError) as exc:
            raise ApiHTTPError(
                status_code=404,
                code="artifact_not_found",
                message="Artifact was not found.",
                details={"artifact_id": artifact_id},
                remediation="Use an artifact ID from a run detail response.",
            ) from exc

    @app.get("/api/puzzles/{puzzle_id}")
    async def get_player_puzzle(puzzle_id: str, request: Request) -> dict[str, Any]:
        services = _services(request)
        public_puzzle = _find_public_puzzle(services.metadata_store, services.artifact_store, puzzle_id)
        if public_puzzle is None:
            raise ApiHTTPError(
                status_code=404,
                code="puzzle_not_found",
                message="Player-safe puzzle was not found.",
                details={"puzzle_id": puzzle_id},
                remediation="Generate a puzzle first or check the puzzle ID from the publish review.",
            )
        return _player_puzzle_response(public_puzzle).to_dict()

    return app


def _json_error(
    *,
    status_code: int,
    code: str,
    message: str,
    request: Request,
    details: dict[str, Any] | None = None,
    remediation: str | None = None,
) -> JSONResponse:
    correlation_id = _correlation_id(request)
    payload = error_response(
        code=code,
        message=message,
        correlation_id=correlation_id,
        details=details,
        remediation=remediation,
    ).to_dict()
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={CORRELATION_ID_HEADER: correlation_id},
    )


def _correlation_id(request: Request) -> str:
    return str(getattr(request.state, "correlation_id", _new_correlation_id()))


def _new_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex}"


def _services(request: Request) -> WebApiServices:
    return request.app.state.services


async def _json_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 - malformed client payloads should produce structured API errors.
        raise ApiHTTPError(
            status_code=400,
            code="invalid_json",
            message="Request body must be valid JSON.",
            remediation="Send a JSON object with the required fields.",
        ) from exc
    if not isinstance(payload, dict):
        raise ApiHTTPError(
            status_code=400,
            code="invalid_payload",
            message="Request body must be a JSON object.",
            remediation="Send a JSON object with the required fields.",
        )
    return payload


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ApiHTTPError(
            status_code=422,
            code="validation_error",
            message=f"{field_name} is required.",
            details={"field": field_name},
            remediation=f"Provide a non-empty {field_name} value.",
        )
    return value.strip()


def _int_query(request: Request, name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = request.query_params.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ApiHTTPError(
            status_code=422,
            code="validation_error",
            message=f"{name} must be an integer.",
            details={"field": name},
        ) from exc
    return max(minimum, min(maximum, value))


def _int_body(payload: dict[str, Any], name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = payload.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ApiHTTPError(
            status_code=422,
            code="validation_error",
            message=f"{name} must be an integer.",
            details={"field": name},
        ) from exc
    if value < minimum or value > maximum:
        raise ApiHTTPError(
            status_code=422,
            code="validation_error",
            message=f"{name} must be between {minimum} and {maximum}.",
            details={"field": name, "minimum": minimum, "maximum": maximum},
        )
    return value


def _string_list_body(payload: dict[str, Any], name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = payload.get(name)
    if raw_value is None:
        return default
    if isinstance(raw_value, str):
        items = (raw_value,)
    elif isinstance(raw_value, list):
        items = tuple(str(item).strip() for item in raw_value if str(item).strip())
    else:
        raise ApiHTTPError(
            status_code=422,
            code="validation_error",
            message=f"{name} must be a string or list of strings.",
            details={"field": name},
        )
    return items or default


def _write_notes_file(settings: Settings, *, theme: str, notes: str) -> Path:
    notes_root = settings.home / "web-notes"
    notes_root.mkdir(parents=True, exist_ok=True)
    slug = "".join(char.lower() if char.isalnum() else "-" for char in theme).strip("-") or "theme"
    path = notes_root / f"{slug}-{uuid.uuid4().hex[:10]}.md"
    path.write_text(notes, encoding="utf-8")
    return path


def _artifact_summary(artifact: ArtifactRecord | dict[str, Any], *, label: str | None = None) -> ArtifactSummary:
    if isinstance(artifact, ArtifactRecord):
        artifact_id = str(artifact.artifact_id)
        media_type = artifact.media_type
        created_at = artifact.created_at
        checksum = None
    else:
        artifact_id = str(artifact["id"])
        media_type = str(artifact["media_type"])
        created_at = str(artifact["created_at"])
        checksum = artifact.get("content_hash")
    return ArtifactSummary(
        artifact_id=artifact_id,
        label=label or _label_for_media_type(media_type),
        media_type=media_type,
        created_at=created_at,
        href=f"/api/artifacts/{artifact_id}",
        checksum=checksum,
    )


def _label_for_media_type(media_type: str) -> str:
    labels = {
        "application/vnd.crosswordai.source-pack+json": "Source pack",
        "application/vnd.crosswordai.core-export-bundle+json": "Export bundle",
        "application/vnd.crosswordai.enterprise-inspection+json": "Inspection bundle",
        "application/vnd.crosswordai.core-eval-gate+json": "Eval gate",
        "application/vnd.crosswordai.trace+json": "Trace",
    }
    return labels.get(media_type, media_type)


def _run_summary(
    run: RunRecord,
    *,
    artifact_count: int,
    theme: str | None = None,
    source_pack_id: str | None = None,
    puzzle_id: str | None = None,
) -> RunSummary:
    return RunSummary(
        run_id=run.id,
        run_type=run.run_type,
        status=run.status,  # type: ignore[arg-type]
        theme=theme or "Untitled theme",
        created_at=run.created_at,
        completed_at=run.completed_at,
        source_pack_id=source_pack_id,
        puzzle_id=puzzle_id,
        artifact_count=artifact_count,
    )


def _source_pack_response_from_detail(detail: dict[str, Any] | None) -> SourcePackResponse:
    if detail is None:
        raise ApiHTTPError(
            status_code=404,
            code="source_pack_not_found",
            message="Source pack was not found.",
            remediation="Check the source pack ID from a run detail response.",
        )
    rights_status = str(detail.get("rights_metadata", {}).get("policy_status") or "unknown")
    return SourcePackResponse(
        source_pack_id=str(detail["id"]),
        theme=str(detail["theme"]),
        taxonomy=str(detail["taxonomy"]),
        taxonomy_confidence=float(detail["taxonomy_confidence"]),
        quality_score=float(detail["quality_score"]),
        document_count=int(detail["document_count"]),
        evidence_snippet_count=int(detail["evidence_snippet_count"]),
        rights_status=rights_status,
        evidence_previews=tuple(
            {
                "evidence_id": snippet["id"],
                "source_document_id": snippet["source_document_id"],
                "snippet_preview": snippet["snippet_preview"],
                "rights_risk": snippet["rights_risk"],
                "allowed_use": snippet["allowed_use"],
            }
            for snippet in detail.get("evidence_snippets", [])
        ),
        vector_notes={"strategy": "hybrid", "source": "local_source_pack", "coverage": detail["quality_score"]},
        graph_summary={"entity_count": 0, "relationship_count": 0},
    )


def _run_detail_response(
    metadata_store: MetadataStore,
    artifact_store: LocalArtifactStore,
    run_id: str,
    *,
    fallback_theme: str | None = None,
    fallback_source_pack_id: str | None = None,
    fallback_puzzle_id: str | None = None,
) -> RunDetailResponse:
    run = metadata_store.get_run(run_id)
    if run is None:
        raise ApiHTTPError(
            status_code=404,
            code="run_not_found",
            message="Run was not found.",
            details={"run_id": run_id},
            remediation="Use a run ID returned by the generation endpoint.",
        )
    artifacts = metadata_store.list_artifacts(run_id=run_id)
    context = _run_context_from_artifacts(artifact_store, artifacts)
    theme = context.get("theme") or fallback_theme
    source_pack_id = context.get("source_pack_id") or fallback_source_pack_id
    puzzle_id = context.get("puzzle_id") or fallback_puzzle_id
    qa_summary = context.get("qa_summary") or {"passed": run.status == "succeeded", "hard_gate_failures": []}
    artifact_summaries = tuple(_artifact_summary(artifact) for artifact in artifacts)
    return RunDetailResponse(
        run=_run_summary(
            run,
            artifact_count=len(artifacts),
            theme=theme,
            source_pack_id=source_pack_id,
            puzzle_id=puzzle_id,
        ),
        stages=_stages_for_run(run, artifacts),
        artifacts=artifact_summaries,
        qa_summary=qa_summary,
        links={
            "player": f"/puzzles/{puzzle_id}" if puzzle_id else None,
            "source_pack": f"/api/source-packs/{source_pack_id}" if source_pack_id else None,
            "report": f"/reports/{run_id}",
        },
    )


def _run_context_from_artifacts(artifact_store: LocalArtifactStore, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for artifact in artifacts:
        media_type = str(artifact["media_type"])
        artifact_id = ArtifactId(str(artifact["id"]))
        try:
            payload = artifact_store.read_json(artifact_id)
        except FileNotFoundError:
            continue
        if media_type == "application/vnd.crosswordai.source-pack+json":
            context.setdefault("theme", payload.get("theme"))
            context.setdefault("source_pack_id", payload.get("id"))
        elif media_type == "application/vnd.crosswordai.core-export-bundle+json":
            context.setdefault("source_pack_id", payload.get("source_pack_id"))
            context.setdefault("puzzle_id", payload.get("puzzle_id"))
            context.setdefault("qa_summary", payload.get("artifacts", {}).get("qa_scorecard"))
        elif media_type == "application/vnd.crosswordai.enterprise-inspection+json":
            context.setdefault("theme", payload.get("theme"))
    return context


def _stages_for_run(run: RunRecord, artifacts: list[dict[str, Any]]) -> tuple[RunStage, ...]:
    media_types = {str(artifact["media_type"]) for artifact in artifacts}
    failed = (run.failure_reason,) if run.failure_reason else ()
    return (
        RunStage(
            "source_pack",
            "Source pack",
            _stage_status("application/vnd.crosswordai.source-pack+json" in media_types, run),
            run.created_at,
            run.completed_at,
            failed if run.run_type == "source_pack_build" and run.status != "succeeded" else (),
        ),
        RunStage("grid", "Grid construction", _stage_status("application/vnd.crosswordai.core-export-bundle+json" in media_types, run)),
        RunStage("clues", "Clue generation and QA", _stage_status("application/vnd.crosswordai.core-export-bundle+json" in media_types, run)),
        RunStage("publish", "Publish gate", _stage_status("application/vnd.crosswordai.core-export-bundle+json" in media_types, run)),
    )


def _stage_status(done: bool, run: RunRecord) -> str:
    if done and run.status == "quarantined":
        return "quarantined"
    if done:
        return "succeeded"
    if run.status == "failed":
        return "failed"
    return "pending"


def _find_public_puzzle(
    metadata_store: MetadataStore,
    artifact_store: LocalArtifactStore,
    puzzle_id: str,
) -> dict[str, Any] | None:
    for run in metadata_store.list_runs(limit=100):
        for artifact in metadata_store.list_artifacts(run_id=run.id):
            if artifact["media_type"] != "application/vnd.crosswordai.core-export-bundle+json":
                continue
            payload = artifact_store.read_json(ArtifactId(str(artifact["id"])))
            public_puzzle = payload.get("artifacts", {}).get("public_puzzle")
            if isinstance(public_puzzle, dict) and public_puzzle.get("puzzle_id") == puzzle_id:
                return public_puzzle
    return None


def _player_puzzle_response(public_puzzle: dict[str, Any]) -> PlayerPuzzleResponse:
    grid_payload = public_puzzle["grid"]
    clues = _player_clues(public_puzzle)
    return PlayerPuzzleResponse(
        puzzle_id=str(public_puzzle["puzzle_id"]),
        title=str(public_puzzle.get("title") or public_puzzle["puzzle_id"]),
        theme=str(public_puzzle.get("theme") or public_puzzle.get("source_pack_id") or "Generated puzzle"),
        status="playable",
        grid=PlayerGrid(
            width=int(grid_payload["width"]),
            height=int(grid_payload["height"]),
            rows=tuple(str(row) for row in grid_payload["rows"]),
        ),
        clues=tuple(clues),
        metadata={
            "source_pack_id": public_puzzle.get("source_pack_id"),
            "difficulty": "standard",
        },
        export_policy={
            "public_safe": True,
            "raw_evidence_quotes_included": False,
            "answer_key_included": False,
        },
    )


def _player_clues(public_puzzle: dict[str, Any]) -> list[PlayerClue]:
    grid_rows = tuple(str(row) for row in public_puzzle["grid"]["rows"])
    positions = _entry_positions(grid_rows)
    clue_payloads = list(public_puzzle.get("clues", []))
    answer_key = list(public_puzzle.get("answer_key", {}).get("answers", []))
    clues: list[PlayerClue] = []
    for index, clue in enumerate(clue_payloads):
        if index >= len(positions):
            break
        position = positions[index]
        key = answer_key[index] if index < len(answer_key) else {}
        clues.append(
            PlayerClue(
                clue_id=str(clue.get("clue_id") or f"clue_{index + 1:03d}"),
                number=position["number"],
                direction=position["direction"],  # type: ignore[arg-type]
                row=position["row"],
                col=position["col"],
                answer_length=int(key.get("enumeration") or position["answer_length"]),
                clue_text=str(clue.get("clue_text") or "Generated clue"),
                difficulty=str(clue.get("difficulty") or "standard"),
                answer_hash=str(clue.get("answer_hash") or key.get("answer_hash") or ""),
                source_evidence_ids=tuple(str(item) for item in clue.get("source_evidence_ids", ())),
            )
        )
    return clues


def _entry_positions(rows: tuple[str, ...]) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    number = 1
    height = len(rows)
    width = len(rows[0]) if rows else 0
    for row in range(height):
        for col in range(width):
            if rows[row][col] == "#":
                continue
            starts_across = col == 0 or rows[row][col - 1] == "#"
            starts_down = row == 0 or rows[row - 1][col] == "#"
            cell_number = number if starts_across or starts_down else None
            if starts_across:
                length = 0
                while col + length < width and rows[row][col + length] != "#":
                    length += 1
                positions.append({"number": cell_number, "direction": "across", "row": row, "col": col, "answer_length": length})
            if starts_down:
                length = 0
                while row + length < height and rows[row + length][col] != "#":
                    length += 1
                positions.append({"number": cell_number, "direction": "down", "row": row, "col": col, "answer_length": length})
            if starts_across or starts_down:
                number += 1
    return positions


app = create_app()
