"""Puzzle-level QA and publish decisions."""

from __future__ import annotations

from dataclasses import dataclass, field

from crosswordai.clues import ClueCandidate, ClueQualityGate, ClueRepairLoop
from crosswordai.solver import AmericanGridValidator, Grid


@dataclass(frozen=True, slots=True)
class ClueQAResult:
    answer: str
    status: str
    failures: tuple[str, ...]
    repair_history: tuple[str, ...]
    quality_score: float
    quarantined: bool


@dataclass(frozen=True, slots=True)
class QAScorecard:
    hard_gate_failures: tuple[str, ...]
    soft_score: float
    clue_results: tuple[ClueQAResult, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.hard_gate_failures and self.soft_score >= 0.7


@dataclass(frozen=True, slots=True)
class PublishDecision:
    status: str
    reasons: tuple[str, ...]
    scorecard: QAScorecard


class ClueQAPipeline:
    def __init__(
        self,
        *,
        quality_gate: ClueQualityGate | None = None,
        repair_loop: ClueRepairLoop | None = None,
    ) -> None:
        self.quality_gate = quality_gate or ClueQualityGate()
        self.repair_loop = repair_loop or ClueRepairLoop(self.quality_gate)

    def evaluate(self, clues: list[ClueCandidate]) -> tuple[list[ClueCandidate], tuple[ClueQAResult, ...]]:
        final_clues: list[ClueCandidate] = []
        results: list[ClueQAResult] = []
        for clue in clues:
            siblings = [other for other in clues if other is not clue]
            repaired = self.repair_loop.repair(clue, sibling_clues=siblings)
            final_clues.append(repaired)
            results.append(
                ClueQAResult(
                    answer=repaired.answer,
                    status=repaired.qa_status,
                    failures=repaired.qa_failures,
                    repair_history=repaired.repair_history,
                    quality_score=_clue_quality_score(repaired),
                    quarantined=repaired.qa_status != "passed",
                )
            )
        return final_clues, tuple(results)


class PuzzleQualityGate:
    def __init__(self, clue_qa: ClueQAPipeline | None = None) -> None:
        self.clue_qa = clue_qa or ClueQAPipeline()

    def evaluate_clues(self, clues: list[ClueCandidate]) -> tuple[list[ClueCandidate], tuple[ClueQAResult, ...]]:
        return self.clue_qa.evaluate(clues)

    def evaluate(self, *, grid: Grid, clues: list[ClueCandidate]) -> QAScorecard:
        failures = list(AmericanGridValidator().validate(grid).failures)
        if not clues:
            failures.append("missing_clues")
        final_clues, clue_results = self.evaluate_clues(clues)
        for result in clue_results:
            if result.quarantined:
                failures.append(f"clue_failed:{result.answer}")
        pass_rate = _pass_rate(clue_results)
        evidence_rate = _evidence_rate(final_clues)
        soft_score = round((pass_rate * 0.7) + (evidence_rate * 0.3), 3) if clues else 0.0
        metrics = {
            "clue_pass_rate": pass_rate,
            "evidence_rate": evidence_rate,
            "avg_clue_quality": _average(result.quality_score for result in clue_results),
        }
        return QAScorecard(tuple(failures), soft_score, clue_results, metrics)

    def publish_decision(self, *, grid: Grid, clues: list[ClueCandidate]) -> PublishDecision:
        scorecard = self.evaluate(grid=grid, clues=clues)
        if scorecard.passed:
            return PublishDecision("published", (), scorecard)
        return PublishDecision("quarantined", scorecard.hard_gate_failures, scorecard)


def _clue_quality_score(clue: ClueCandidate) -> float:
    score = 1.0
    score -= len(clue.qa_failures) * 0.18
    score -= max(0.0, clue.ambiguity_score - 0.25) * 0.4
    score += min(0.15, max(0.0, clue.fact_confidence - 0.65) * 0.3)
    if clue.repair_history:
        score -= 0.05
    return round(min(1.0, max(0.0, score)), 3)


def _pass_rate(results: tuple[ClueQAResult, ...]) -> float:
    if not results:
        return 0.0
    return round(sum(1 for result in results if not result.quarantined) / len(results), 3)


def _evidence_rate(clues: list[ClueCandidate]) -> float:
    if not clues:
        return 0.0
    return round(sum(1 for clue in clues if clue.source_evidence_ids and clue.evidence_quotes) / len(clues), 3)


def _average(values: object) -> float:
    numbers = list(values)
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 3)
