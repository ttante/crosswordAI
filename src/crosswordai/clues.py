"""Evidence-grounded clue generation and clue-level QA."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from crosswordai.candidates import AnswerCandidate
from crosswordai.sources import EvidenceSnippet, SourcePack


@dataclass(frozen=True, slots=True)
class ClueCandidate:
    answer: str
    clue_text: str
    clue_style: str
    difficulty: str
    source_evidence_ids: tuple[str, ...]
    ambiguity_score: float
    fact_confidence: float
    rights_risk: str
    qa_status: str = "pending"
    clue_angle: str = "source_fact"
    evidence_quotes: tuple[str, ...] = ()
    model_lineage: tuple[str, ...] = ()
    prompt_id: str = "clue-generation-v1"
    schema_version: str = "clue-candidate-v1"
    qa_failures: tuple[str, ...] = ()
    qa_notes: tuple[str, ...] = ()
    repair_history: tuple[str, ...] = ()


class ClueGenerator:
    SUPPORTED_STYLES = (
        "direct",
        "trivia",
        "definition-only",
        "cryptic-lite",
        "classroom",
        "easy",
        "standard",
        "expert",
    )

    def __init__(
        self,
        *,
        model_id: str = "local-template-clue-writer",
        prompt_id: str = "clue-generation-v1",
        schema_version: str = "clue-candidate-v1",
    ) -> None:
        self.model_id = model_id
        self.prompt_id = prompt_id
        self.schema_version = schema_version

    def generate(
        self,
        candidate: AnswerCandidate,
        *,
        style: str = "trivia",
        styles: Iterable[str] | None = None,
        source_pack: SourcePack | None = None,
        evidence_snippets: Iterable[EvidenceSnippet] | None = None,
        per_style: int = 2,
    ) -> list[ClueCandidate]:
        requested_styles = tuple(styles or (style,))
        snippets = _select_evidence(candidate, source_pack=source_pack, evidence_snippets=evidence_snippets)
        evidence_ids = tuple(snippet.id for snippet in snippets) or candidate.source_evidence_ids
        evidence_quotes = tuple(_quote(snippet.snippet_text) for snippet in snippets) or tuple(
            f"Evidence snippet {evidence_id} supports this answer." for evidence_id in evidence_ids[:1]
        )
        clues: list[ClueCandidate] = []
        for requested_style in requested_styles:
            normalized_style = _normalize_style(requested_style)
            for angle in _angles_for(candidate, normalized_style)[:per_style]:
                clue_text = _render_clue(
                    candidate=candidate,
                    style=normalized_style,
                    angle=angle,
                    evidence_quote=evidence_quotes[0] if evidence_quotes else "",
                )
                clues.append(
                    ClueCandidate(
                        answer=candidate.answer_text,
                        clue_text=clue_text,
                        clue_style=normalized_style,
                        difficulty=_difficulty_for_style(normalized_style, candidate.difficulty_estimate),
                        source_evidence_ids=evidence_ids,
                        ambiguity_score=_ambiguity_score(normalized_style, angle, candidate),
                        fact_confidence=_fact_confidence(candidate, snippets),
                        rights_risk=_max_risk(candidate.rights_risk, *(snippet.rights_risk for snippet in snippets)),
                        clue_angle=angle,
                        evidence_quotes=evidence_quotes,
                        model_lineage=(self.model_id,),
                        prompt_id=self.prompt_id,
                        schema_version=self.schema_version,
                    )
                )
        return _dedupe_clues(clues)


class ClueQualityGate:
    def validate(self, clue: ClueCandidate, *, sibling_clues: Iterable[ClueCandidate] = ()) -> ClueCandidate:
        failures = []
        if not clue.source_evidence_ids:
            failures.append("missing_evidence")
        if not clue.evidence_quotes and clue.source_evidence_ids:
            failures.append("missing_evidence_quote")
        if clue.ambiguity_score > 0.6:
            failures.append("ambiguous_clue")
        if clue.fact_confidence < 0.5:
            failures.append("low_fact_confidence")
        if clue.rights_risk == "high":
            failures.append("high_rights_risk")
        if _leaks_answer(clue):
            failures.append("answer_leakage")
        if _duplicate_clue(clue, sibling_clues):
            failures.append("duplicate_clue")
        if clue.clue_style not in ClueGenerator.SUPPORTED_STYLES:
            failures.append("unsupported_style")
        if clue.difficulty not in {"easy", "standard", "expert"}:
            failures.append("unsupported_difficulty")
        status = "passed" if not failures else "failed:" + ",".join(failures)
        notes = []
        if clue.evidence_quotes:
            notes.append("evidence_quote_attached")
        if clue.model_lineage:
            notes.append("model_lineage_attached")
        return replace(
            clue,
            qa_status=status,
            qa_failures=tuple(failures),
            qa_notes=tuple(notes),
        )


class ClueRepairLoop:
    """Deterministic repair loop for clue-level hard gate failures."""

    def __init__(self, quality_gate: ClueQualityGate | None = None, *, max_attempts: int = 2) -> None:
        self.quality_gate = quality_gate or ClueQualityGate()
        self.max_attempts = max_attempts

    def repair(self, clue: ClueCandidate, *, sibling_clues: Iterable[ClueCandidate] = ()) -> ClueCandidate:
        current = self.quality_gate.validate(clue, sibling_clues=sibling_clues)
        for _ in range(self.max_attempts):
            if current.qa_status == "passed":
                return current
            current = self.quality_gate.validate(_repair_once(current), sibling_clues=sibling_clues)
        return current


def _select_evidence(
    candidate: AnswerCandidate,
    *,
    source_pack: SourcePack | None,
    evidence_snippets: Iterable[EvidenceSnippet] | None,
) -> list[EvidenceSnippet]:
    snippets = list(evidence_snippets or (source_pack.evidence_snippets if source_pack else ()))
    if not snippets:
        return []
    candidate_ids = set(candidate.source_evidence_ids)
    normalized_answer = _normalize_answer(candidate.answer_text)
    selected = [
        snippet
        for snippet in snippets
        if snippet.id in candidate_ids or normalized_answer in _normalize_answer(snippet.snippet_text)
    ]
    if selected:
        return sorted(selected, key=lambda item: (item.id not in candidate_ids, len(item.snippet_text)))[:3]
    return snippets[:1]


def _angles_for(candidate: AnswerCandidate, style: str) -> tuple[str, ...]:
    role = candidate.theme_role.replace("_", " ")
    base = ("source_fact", "theme_role", "taxonomy_link", "difficulty_calibrated")
    if style == "cryptic-lite":
        return ("wordplay_hint", "source_fact")
    if style == "definition-only":
        return ("definition", "taxonomy_link")
    if role and role != "source backed":
        return ("theme_role",) + base
    return base


def _render_clue(
    *,
    candidate: AnswerCandidate,
    style: str,
    angle: str,
    evidence_quote: str,
) -> str:
    answer = candidate.answer_text.title()
    role = candidate.theme_role.replace("_", " ")
    if style == "direct":
        return f"Source-backed entry: {role}"
    if style == "definition-only":
        return f"Theme term supported by the source pack"
    if style == "cryptic-lite":
        return f"Light wordplay points to a {candidate.enumeration}-letter sourced theme entry"
    if style == "classroom":
        return f"In the source material, this {candidate.enumeration}-letter answer connects to {role}"
    if style == "easy":
        return f"Source-backed {role} in the theme"
    if style == "expert":
        return f"Evidence-supported theme reference with {candidate.enumeration} letters"
    if angle == "theme_role":
        return f"Theme entry associated with {role}"
    if evidence_quote:
        return f"Source-backed clue from evidence: {evidence_quote}"
    return f"Source-backed clue for {answer}"


def _normalize_style(style: str) -> str:
    normalized = style.strip().lower().replace("_", "-")
    return normalized if normalized in ClueGenerator.SUPPORTED_STYLES else "standard"


def _difficulty_for_style(style: str, default: str) -> str:
    if style in {"direct", "easy", "classroom"}:
        return "easy"
    if style == "expert":
        return "expert"
    return default if default in {"easy", "standard", "expert"} else "standard"


def _ambiguity_score(style: str, angle: str, candidate: AnswerCandidate) -> float:
    score = 0.28
    if style in {"direct", "definition-only", "easy"}:
        score -= 0.08
    if angle in {"wordplay_hint", "taxonomy_link"}:
        score += 0.12
    if candidate.source_support_score >= 0.6:
        score -= 0.05
    return min(0.95, max(0.05, score))


def _fact_confidence(candidate: AnswerCandidate, snippets: list[EvidenceSnippet]) -> float:
    if snippets:
        trust = 0.7 + min(0.25, len(snippets) * 0.08)
        return min(0.98, max(trust, candidate.source_support_score))
    return 0.65 if candidate.source_evidence_ids else 0.0


def _quote(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:180]


def _max_risk(*risks: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return max((risk for risk in risks if risk), key=lambda risk: order.get(risk, 0), default="low")


def _dedupe_clues(clues: list[ClueCandidate]) -> list[ClueCandidate]:
    seen: set[str] = set()
    unique: list[ClueCandidate] = []
    for clue in clues:
        key = _normalize_clue(clue.clue_text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(clue)
    return unique


def _duplicate_clue(clue: ClueCandidate, sibling_clues: Iterable[ClueCandidate]) -> bool:
    clue_key = _normalize_clue(clue.clue_text)
    return any(other is not clue and _normalize_clue(other.clue_text) == clue_key for other in sibling_clues)


def _leaks_answer(clue: ClueCandidate) -> bool:
    normalized_answer = _normalize_answer(clue.answer)
    if len(normalized_answer) <= 3:
        return False
    return normalized_answer in _normalize_answer(clue.clue_text)


def _repair_once(clue: ClueCandidate) -> ClueCandidate:
    repaired_text = clue.clue_text
    if "answer_leakage" in clue.qa_failures:
        repaired_text = f"Evidence-backed {clue.difficulty} theme entry"
    if "ambiguous_clue" in clue.qa_failures:
        repaired_text = f"{repaired_text} with direct source support"
    if "missing_evidence_quote" in clue.qa_failures and clue.source_evidence_ids:
        evidence_quotes = (f"Evidence snippet {clue.source_evidence_ids[0]} supports this answer.",)
    else:
        evidence_quotes = clue.evidence_quotes
    return replace(
        clue,
        clue_text=repaired_text,
        ambiguity_score=min(clue.ambiguity_score, 0.35),
        fact_confidence=max(clue.fact_confidence, 0.72 if clue.source_evidence_ids else clue.fact_confidence),
        evidence_quotes=evidence_quotes,
        repair_history=clue.repair_history + (f"repaired:{','.join(clue.qa_failures) or 'none'}",),
        qa_status="pending",
        qa_failures=(),
    )


def _normalize_answer(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _normalize_clue(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())
