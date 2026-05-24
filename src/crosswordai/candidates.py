"""Answer candidate generation from source packs, graph facts, and retrieval evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from crosswordai.graph import KnowledgeGraph
from crosswordai.sources import SourcePack
from crosswordai.vectors import HashingEmbeddingModel, SearchResult


@dataclass(frozen=True, slots=True)
class AnswerCandidate:
    answer_text: str
    normalized_answer: str
    enumeration: int
    theme_role: str
    difficulty_estimate: str
    familiarity_score: float
    novelty_score: float
    rights_risk: str
    source_evidence_ids: tuple[str, ...]
    source_support_score: float = 0.0
    taxonomy_tags: tuple[str, ...] = ()
    generation_source: str = "source_pack"
    duplicate_group: str | None = None


class CandidateGenerator:
    def __init__(
        self,
        embedding_model: HashingEmbeddingModel | None = None,
        *,
        similarity_threshold: float = 0.92,
        min_source_support: float = 0.2,
    ) -> None:
        self.embedding_model = embedding_model or HashingEmbeddingModel()
        self.similarity_threshold = similarity_threshold
        self.min_source_support = min_source_support

    def from_source_pack(
        self,
        source_pack: SourcePack,
        *,
        graph: KnowledgeGraph | None = None,
        retrieval_results: list[SearchResult] | None = None,
        limit: int = 50,
    ) -> list[AnswerCandidate]:
        raw_candidates: list[AnswerCandidate] = []
        evidence_by_phrase: dict[str, list[str]] = {}
        risk_by_phrase: dict[str, str] = {}
        for snippet in source_pack.evidence_snippets:
            for phrase in _extract_phrases(snippet.snippet_text):
                evidence_by_phrase.setdefault(phrase, []).append(snippet.id)
                risk_by_phrase[phrase] = _max_risk(risk_by_phrase.get(phrase, "low"), snippet.rights_risk)

        taxonomy_tags = tuple(str(tag) for tag in source_pack.taxonomy_metadata.get("required_entities", []))
        for phrase, evidence_ids in evidence_by_phrase.items():
            raw_candidates.append(
                self._candidate(
                    phrase=phrase,
                    evidence_ids=evidence_ids,
                    rights_risk=risk_by_phrase.get(phrase, "low"),
                    taxonomy_tags=taxonomy_tags,
                    generation_source="source_pack",
                    theme_role=_theme_role_for(source_pack.taxonomy, phrase),
                )
            )

        if graph is not None:
            for entity in graph.entities.values():
                if entity.source_pack_id != str(source_pack.id):
                    continue
                raw_candidates.append(
                    self._candidate(
                        phrase=entity.name,
                        evidence_ids=list(entity.source_evidence_ids),
                        rights_risk="low",
                        taxonomy_tags=(entity.entity_type,),
                        generation_source="knowledge_graph",
                        theme_role=f"graph_{entity.entity_type}",
                        confidence_boost=entity.confidence,
                    )
                )
            for relationship in graph.relationships:
                if relationship.source_pack_id != str(source_pack.id):
                    continue
                if relationship.object_id in graph.entities:
                    obj = graph.entities[relationship.object_id]
                    raw_candidates.append(
                        self._candidate(
                            phrase=obj.name,
                            evidence_ids=list(relationship.source_evidence_ids),
                            rights_risk="low",
                            taxonomy_tags=(relationship.predicate,),
                            generation_source="knowledge_graph_relationship",
                            theme_role=f"relationship_{relationship.predicate}",
                            confidence_boost=relationship.confidence,
                        )
                    )

        for result in retrieval_results or []:
            evidence_id = result.metadata.get("evidence_snippet_id", result.id)
            for phrase in _extract_phrases(result.text):
                raw_candidates.append(
                    self._candidate(
                        phrase=phrase,
                        evidence_ids=[evidence_id],
                        rights_risk=result.metadata.get("rights_risk", "low"),
                        taxonomy_tags=(result.metadata.get("taxonomy", source_pack.taxonomy),),
                        generation_source="retrieval",
                        theme_role="retrieved_evidence",
                        confidence_boost=max(0.0, result.score),
                    )
                )

        filtered = [candidate for candidate in raw_candidates if candidate.source_support_score >= self.min_source_support]
        deduped = self._dedupe(filtered)
        return sorted(
            deduped,
            key=lambda item: (
                -item.source_support_score,
                -item.familiarity_score,
                item.rights_risk,
                item.answer_text,
            ),
        )[:limit]

    def _candidate(
        self,
        *,
        phrase: str,
        evidence_ids: list[str],
        rights_risk: str,
        taxonomy_tags: tuple[str, ...],
        generation_source: str,
        theme_role: str,
        confidence_boost: float = 0.0,
    ) -> AnswerCandidate:
        normalized = _normalize_answer(phrase)
        source_support = min(1.0, len(set(evidence_ids)) * 0.25 + confidence_boost * 0.35)
        familiarity = min(1.0, 0.35 + len(set(evidence_ids)) * 0.12 + confidence_boost * 0.25)
        return AnswerCandidate(
            answer_text=phrase.upper(),
            normalized_answer=normalized,
            enumeration=len(normalized),
            theme_role=theme_role,
            difficulty_estimate=_difficulty_for(phrase),
            familiarity_score=familiarity,
            novelty_score=_novelty_for(phrase),
            rights_risk=rights_risk,
            source_evidence_ids=tuple(sorted(set(evidence_ids))),
            source_support_score=source_support,
            taxonomy_tags=taxonomy_tags,
            generation_source=generation_source,
        )

    def _dedupe(self, candidates: list[AnswerCandidate]) -> list[AnswerCandidate]:
        kept: list[AnswerCandidate] = []
        vectors: list[tuple[float, ...]] = []
        for candidate in sorted(candidates, key=lambda item: (-item.source_support_score, item.answer_text)):
            if not candidate.normalized_answer:
                continue
            vector = self.embedding_model.embed(candidate.answer_text)
            duplicate_index = _find_duplicate(candidate, vector, kept, vectors, self.similarity_threshold)
            if duplicate_index is None:
                kept.append(candidate)
                vectors.append(vector)
                continue
            existing = kept[duplicate_index]
            merged_evidence = tuple(sorted(set(existing.source_evidence_ids + candidate.source_evidence_ids)))
            better = existing if existing.source_support_score >= candidate.source_support_score else candidate
            kept[duplicate_index] = replace(
                better,
                source_evidence_ids=merged_evidence,
                source_support_score=max(existing.source_support_score, candidate.source_support_score),
                familiarity_score=max(existing.familiarity_score, candidate.familiarity_score),
                duplicate_group=existing.normalized_answer,
            )
        return kept


def _extract_phrases(text: str) -> list[str]:
    phrases = re.findall(r"\b(?:[A-Z][a-z0-9]+(?:\s+(?:of|the|and|[A-Z][a-z0-9]+)){0,4})\b", text)
    return [phrase.strip() for phrase in phrases if len(_normalize_answer(phrase)) >= 3]


def _normalize_answer(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _difficulty_for(phrase: str) -> str:
    length = len(_normalize_answer(phrase))
    if length <= 5:
        return "easy"
    if length <= 10:
        return "standard"
    return "expert"


def _theme_role_for(taxonomy: str, phrase: str) -> str:
    if taxonomy == "music_artist" and any(word in phrase.lower() for word in ["album", "song", "jazz"]):
        return "music_theme_entry"
    if taxonomy == "technical_topic":
        return "technical_term"
    return "source_backed"


def _novelty_for(phrase: str) -> float:
    words = phrase.split()
    return min(1.0, 0.35 + len(words) * 0.12)


def _max_risk(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _find_duplicate(
    candidate: AnswerCandidate,
    vector: tuple[float, ...],
    kept: list[AnswerCandidate],
    vectors: list[tuple[float, ...]],
    threshold: float,
) -> int | None:
    for index, existing in enumerate(kept):
        if candidate.normalized_answer == existing.normalized_answer:
            return index
        if candidate.normalized_answer in existing.normalized_answer or existing.normalized_answer in candidate.normalized_answer:
            return index
        if _cosine(vector, vectors[index]) >= threshold:
            return index
    return None


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
