"""Deterministic web contract fixtures used by API and frontend tests."""

from __future__ import annotations

from typing import Any

from crosswordai.web_contracts import (
    ArtifactSummary,
    BatchSummaryResponse,
    PlayerClue,
    PlayerGrid,
    PlayerPuzzleResponse,
    RegistryIndexResponse,
    ReportSummaryResponse,
    RunDetailResponse,
    RunStage,
    RunSummary,
    SourcePackResponse,
)


FIXTURE_TIME = "2026-05-24T00:00:00+00:00"


def sample_artifact() -> ArtifactSummary:
    return ArtifactSummary(
        artifact_id="art_web_fixture_export",
        label="Public puzzle export",
        media_type="application/vnd.crosswordai.core-export-bundle+json",
        created_at=FIXTURE_TIME,
        href="/api/artifacts/art_web_fixture_export",
        checksum="sha256:fixture",
    )


def sample_run_detail() -> RunDetailResponse:
    return RunDetailResponse(
        run=RunSummary(
            run_id="run_web_fixture",
            run_type="hardened_core_path",
            status="succeeded",
            theme="Miles Davis",
            created_at=FIXTURE_TIME,
            completed_at=FIXTURE_TIME,
            source_pack_id="sp_web_fixture",
            puzzle_id="puzzle_web_fixture",
            artifact_count=3,
        ),
        stages=(
            RunStage("source_pack", "Source pack", "succeeded", FIXTURE_TIME, FIXTURE_TIME, artifact_ids=("art_source",)),
            RunStage("grid", "Grid construction", "succeeded", FIXTURE_TIME, FIXTURE_TIME),
            RunStage("clues", "Clue generation and QA", "succeeded", FIXTURE_TIME, FIXTURE_TIME),
            RunStage("publish", "Publish gate", "succeeded", FIXTURE_TIME, FIXTURE_TIME, artifact_ids=("art_web_fixture_export",)),
        ),
        artifacts=(sample_artifact(),),
        qa_summary={
            "passed": True,
            "hard_gate_failures": [],
            "soft_score": 0.95,
            "metrics": {"rights_risk": "low", "ambiguity": 0.08},
        },
        links={"player": "/puzzles/puzzle_web_fixture", "source_pack": "/api/source-packs/sp_web_fixture"},
    )


def sample_source_pack() -> SourcePackResponse:
    return SourcePackResponse(
        source_pack_id="sp_web_fixture",
        theme="Miles Davis",
        taxonomy="music_artist",
        taxonomy_confidence=0.94,
        quality_score=0.91,
        document_count=2,
        evidence_snippet_count=4,
        rights_status="reviewed_low_risk",
        evidence_previews=(
            {
                "evidence_id": "ev_kind_of_blue",
                "source_title": "Curated notes",
                "snippet_preview": "Kind of Blue is represented as a source-supported album reference.",
                "rights_risk": "low",
            },
        ),
        vector_notes={"strategy": "hybrid", "top_k": 8, "coverage": 0.88},
        graph_summary={"entity_count": 4, "relationship_count": 3},
    )


def sample_player_puzzle() -> PlayerPuzzleResponse:
    return PlayerPuzzleResponse(
        puzzle_id="puzzle_web_fixture",
        title="Miles Davis Mini",
        theme="Miles Davis",
        status="playable",
        grid=PlayerGrid(width=5, height=5, rows=("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY")),
        clues=(
            PlayerClue(
                clue_id="clue_001",
                number=1,
                direction="across",
                row=0,
                col=0,
                answer_length=5,
                clue_text="Theme-supported entry from the generated grid",
                difficulty="easy",
                answer_hash="f0393febc2f11b59",
                source_evidence_ids=("ev_kind_of_blue",),
            ),
            PlayerClue(
                clue_id="clue_002",
                number=1,
                direction="down",
                row=0,
                col=0,
                answer_length=5,
                clue_text="Crossing entry with source-backed clue metadata",
                difficulty="easy",
                answer_hash="d5ce8ba10a7acb7d",
                source_evidence_ids=("ev_kind_of_blue",),
            ),
        ),
        metadata={
            "difficulty": "easy",
            "source_pack_id": "sp_web_fixture",
            "run_id": "run_web_fixture",
            "created_at": FIXTURE_TIME,
        },
        export_policy={
            "public_safe": True,
            "raw_evidence_quotes_included": False,
            "answer_key_included": False,
        },
    )


def sample_registry_index() -> RegistryIndexResponse:
    return RegistryIndexResponse(
        registries={
            "models": {"mock-local": "1"},
            "routes": {"baseline-local": "1"},
            "prompts": {"clue_candidate": "1"},
            "policies": {"rights-safe-v1": "1"},
        },
        warnings=(),
    )


def sample_batch_summary() -> BatchSummaryResponse:
    return BatchSummaryResponse(
        batch_id="batch_web_fixture",
        status="succeeded",
        created_at=FIXTURE_TIME,
        routes=("baseline-local", "cheap-first-cascade"),
        theme_count=2,
        summary={"succeeded": 2, "failed": 0, "quarantined": 0, "estimated_cost": 0.0},
        artifacts=(sample_artifact(),),
    )


def sample_report_summary() -> ReportSummaryResponse:
    return ReportSummaryResponse(
        run_id="run_web_fixture",
        puzzle_id="puzzle_web_fixture",
        source_coverage={"source_diversity": 2, "retrieval_precision": 0.9, "coverage_gaps": []},
        model_contribution={"baseline-local:local-template": {"clue_count": 2, "estimated_cost": 0.0}},
        qa_scorecard={"passed": True, "soft_score": 0.95, "hard_gate_failures": []},
        links={"inspection_bundle": "/api/reports/run_web_fixture"},
    )


def all_contract_fixtures() -> dict[str, Any]:
    return {
        "artifact": sample_artifact().to_dict(),
        "run_detail": sample_run_detail().to_dict(),
        "source_pack": sample_source_pack().to_dict(),
        "player_puzzle": sample_player_puzzle().to_dict(),
        "registry_index": sample_registry_index().to_dict(),
        "batch_summary": sample_batch_summary().to_dict(),
        "report_summary": sample_report_summary().to_dict(),
    }
