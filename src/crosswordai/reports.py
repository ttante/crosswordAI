"""Inspection reports and polished demo artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from crosswordai.clues import ClueCandidate
from crosswordai.qa import PublishDecision
from crosswordai.solver import Grid


def puzzle_card(*, puzzle_id: str, theme: str, decision: PublishDecision, model_route: str) -> dict[str, Any]:
    return {
        "puzzle_id": puzzle_id,
        "theme": theme,
        "status": decision.status,
        "model_route": model_route,
        "soft_score": decision.scorecard.soft_score,
        "hard_gate_failures": list(decision.scorecard.hard_gate_failures),
        "clue_pass_rate": decision.scorecard.metrics.get("clue_pass_rate", 0.0),
        "recommended_action": "publish" if decision.status == "published" else "repair_or_regenerate",
    }


def quarantine_postmortem(decision: PublishDecision) -> dict[str, Any]:
    return {
        "status": decision.status,
        "root_causes": list(decision.reasons),
        "scorecard": asdict(decision.scorecard),
        "recommended_action": "repair_or_regenerate" if decision.reasons else "none",
    }


@dataclass(frozen=True, slots=True)
class HeatmapCell:
    row: int
    col: int
    value: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClueLineageRow:
    clue_id: str
    answer_hash: str
    clue_style: str
    source_evidence_ids: tuple[str, ...]
    model_lineage: tuple[str, ...]
    qa_status: str
    repair_count: int


@dataclass(frozen=True, slots=True)
class SourceCoverageRow:
    source_pack_id: str
    evidence_id: str
    clue_count: int
    answer_hashes: tuple[str, ...]
    rights_risk: str


@dataclass(frozen=True, slots=True)
class ModelContributionRow:
    model_id: str
    clue_count: int
    passed_count: int
    avg_fact_confidence: float
    avg_ambiguity_score: float


@dataclass(frozen=True, slots=True)
class TaxonomyDriftReport:
    baseline_taxonomy: str
    observed_taxonomies: tuple[str, ...]
    drift_score: float
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelCard:
    model_id: str
    task_types: tuple[str, ...]
    usage_count: int
    avg_quality: float
    avg_cost: float
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EnterpriseInspectionBundle:
    puzzle_card: dict[str, Any]
    quality_heatmap: tuple[HeatmapCell, ...]
    clue_lineage: tuple[ClueLineageRow, ...]
    source_coverage: tuple[SourceCoverageRow, ...]
    model_contribution: tuple[ModelContributionRow, ...]
    taxonomy_drift: TaxonomyDriftReport
    model_cards: tuple[ModelCard, ...]
    quarantine_postmortem: dict[str, Any] | None = None
    export_metadata: dict[str, str] = field(default_factory=dict)


def puzzle_quality_heatmap(*, grid: Grid, clues: list[ClueCandidate]) -> tuple[HeatmapCell, ...]:
    clue_by_answer = {clue.answer: clue for clue in clues}
    cells: list[HeatmapCell] = []
    for row_index, row in enumerate(grid.rows):
        for col_index, char in enumerate(row):
            if char == "#":
                cells.append(HeatmapCell(row_index, col_index, 0.0, ("block",)))
                continue
            related_clues = [clue for answer, clue in clue_by_answer.items() if char.upper() in answer.upper()]
            if not related_clues:
                cells.append(HeatmapCell(row_index, col_index, 0.45, ("unchecked_report_context",)))
                continue
            avg_quality = sum(_clue_quality(clue) for clue in related_clues) / len(related_clues)
            reasons = tuple(sorted({failure for clue in related_clues for failure in clue.qa_failures}))
            cells.append(HeatmapCell(row_index, col_index, round(avg_quality, 3), reasons))
    return tuple(cells)


def clue_lineage_report(clues: list[ClueCandidate]) -> tuple[ClueLineageRow, ...]:
    return tuple(
        ClueLineageRow(
            clue_id=f"clue_{index:03d}",
            answer_hash=_hash_answer(clue.answer),
            clue_style=clue.clue_style,
            source_evidence_ids=clue.source_evidence_ids,
            model_lineage=clue.model_lineage,
            qa_status=clue.qa_status,
            repair_count=len(clue.repair_history),
        )
        for index, clue in enumerate(clues, start=1)
    )


def source_coverage_report(*, source_pack_id: str, clues: list[ClueCandidate]) -> tuple[SourceCoverageRow, ...]:
    coverage: dict[str, dict[str, Any]] = {}
    for clue in clues:
        for evidence_id in clue.source_evidence_ids:
            row = coverage.setdefault(
                evidence_id,
                {"answer_hashes": set(), "clue_count": 0, "rights_risk": "low"},
            )
            row["answer_hashes"].add(_hash_answer(clue.answer))
            row["clue_count"] += 1
            row["rights_risk"] = _max_risk(row["rights_risk"], clue.rights_risk)
    return tuple(
        SourceCoverageRow(
            source_pack_id=source_pack_id,
            evidence_id=evidence_id,
            clue_count=int(row["clue_count"]),
            answer_hashes=tuple(sorted(row["answer_hashes"])),
            rights_risk=str(row["rights_risk"]),
        )
        for evidence_id, row in sorted(coverage.items())
    )


def model_contribution_report(clues: list[ClueCandidate]) -> tuple[ModelContributionRow, ...]:
    grouped: dict[str, list[ClueCandidate]] = {}
    for clue in clues:
        for model_id in clue.model_lineage or ("unknown",):
            grouped.setdefault(model_id, []).append(clue)
    return tuple(
        ModelContributionRow(
            model_id=model_id,
            clue_count=len(items),
            passed_count=sum(1 for clue in items if clue.qa_status == "passed"),
            avg_fact_confidence=_average(clue.fact_confidence for clue in items),
            avg_ambiguity_score=_average(clue.ambiguity_score for clue in items),
        )
        for model_id, items in sorted(grouped.items())
    )


def taxonomy_drift_report(
    *,
    baseline_taxonomy: str,
    observed_taxonomies: tuple[str, ...],
) -> TaxonomyDriftReport:
    if not observed_taxonomies:
        return TaxonomyDriftReport(baseline_taxonomy, (), 0.0, ("missing_observed_taxonomy",))
    mismatches = sum(1 for taxonomy in observed_taxonomies if taxonomy != baseline_taxonomy)
    drift_score = round(mismatches / len(observed_taxonomies), 3)
    warnings = ("taxonomy_drift_detected",) if drift_score > 0.25 else ()
    return TaxonomyDriftReport(baseline_taxonomy, observed_taxonomies, drift_score, warnings)


def model_cards_from_contributions(
    contributions: tuple[ModelContributionRow, ...],
    *,
    task_type: str = "clue_generation",
) -> tuple[ModelCard, ...]:
    cards = []
    for row in contributions:
        avg_quality = round((row.avg_fact_confidence + (1.0 - row.avg_ambiguity_score)) / 2, 3)
        limitations = []
        if row.avg_fact_confidence < 0.7:
            limitations.append("needs_fact_confidence_calibration")
        if row.avg_ambiguity_score > 0.45:
            limitations.append("needs_ambiguity_reduction")
        cards.append(
            ModelCard(
                model_id=row.model_id,
                task_types=(task_type,),
                usage_count=row.clue_count,
                avg_quality=avg_quality,
                avg_cost=0.0,
                limitations=tuple(limitations),
            )
        )
    return tuple(cards)


def enterprise_inspection_bundle(
    *,
    puzzle_id: str,
    theme: str,
    grid: Grid,
    clues: list[ClueCandidate],
    decision: PublishDecision,
    source_pack_id: str,
    model_route: str,
    baseline_taxonomy: str,
    observed_taxonomies: tuple[str, ...],
) -> EnterpriseInspectionBundle:
    contributions = model_contribution_report(clues)
    return EnterpriseInspectionBundle(
        puzzle_card=puzzle_card(puzzle_id=puzzle_id, theme=theme, decision=decision, model_route=model_route),
        quality_heatmap=puzzle_quality_heatmap(grid=grid, clues=clues),
        clue_lineage=clue_lineage_report(clues),
        source_coverage=source_coverage_report(source_pack_id=source_pack_id, clues=clues),
        model_contribution=contributions,
        taxonomy_drift=taxonomy_drift_report(
            baseline_taxonomy=baseline_taxonomy,
            observed_taxonomies=observed_taxonomies,
        ),
        model_cards=model_cards_from_contributions(contributions),
        quarantine_postmortem=quarantine_postmortem(decision) if decision.status != "published" else None,
        export_metadata={
            "bundle_type": "enterprise_inspection",
            "source_pack_id": source_pack_id,
            "public_safe": "true",
        },
    )


def report_export_payload(bundle: EnterpriseInspectionBundle) -> dict[str, Any]:
    return {
        "puzzle_card": bundle.puzzle_card,
        "quality_heatmap": [asdict(cell) for cell in bundle.quality_heatmap],
        "clue_lineage": [asdict(row) for row in bundle.clue_lineage],
        "source_coverage": [asdict(row) for row in bundle.source_coverage],
        "model_contribution": [asdict(row) for row in bundle.model_contribution],
        "taxonomy_drift": asdict(bundle.taxonomy_drift),
        "model_cards": [asdict(card) for card in bundle.model_cards],
        "quarantine_postmortem": bundle.quarantine_postmortem,
        "export_metadata": dict(bundle.export_metadata),
    }


def _clue_quality(clue: ClueCandidate) -> float:
    score = clue.fact_confidence * 0.65 + (1.0 - clue.ambiguity_score) * 0.35
    score -= len(clue.qa_failures) * 0.1
    return min(1.0, max(0.0, score))


def _hash_answer(answer: str) -> str:
    import hashlib

    normalized = "".join(char for char in answer.upper() if char.isalnum())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _average(values: Any) -> float:
    numbers = list(values)
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 3)


def _max_risk(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right
