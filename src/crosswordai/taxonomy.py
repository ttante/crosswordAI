"""Taxonomy classification and retrieval policy defaults."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TaxonomyResult:
    taxonomy: str
    confidence: float
    required_entities: tuple[str, ...]
    preferred_sources: tuple[str, ...]
    rights_threshold: str
    version: str = "0.1.0"
    retrieval_policy: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class TaxonomyDefinition:
    id: str
    version: str
    keywords: tuple[str, ...]
    required_entities: tuple[str, ...]
    preferred_sources: tuple[str, ...]
    retrieval_policy: dict[str, object]

    @property
    def rights_threshold(self) -> str:
        return str(self.retrieval_policy.get("rights_threshold", "standard"))


class RuleBasedTaxonomyClassifier:
    """Deterministic baseline to be replaced or augmented by model routes."""

    def __init__(self, definitions: list[TaxonomyDefinition] | None = None) -> None:
        self.definitions = definitions or load_taxonomy_definitions(Path("config/taxonomies.json"))
        self.by_id = {definition.id: definition for definition in self.definitions}

    def classify(self, theme: str, text: str = "") -> TaxonomyResult:
        haystack = f"{theme}\n{text}".lower()
        scored: list[tuple[int, TaxonomyDefinition]] = []
        for definition in self.definitions:
            score = sum(1 for keyword in definition.keywords if keyword.lower() in haystack)
            if definition.id == "historical_subject" and re.search(r"\b(century|war|revolution|empire|president|king|queen)\b", haystack):
                score += 1
            scored.append((score, definition))
        best_score, best = max(scored, key=lambda item: item[0])
        if best_score == 0:
            best = self.by_id["general_concept"]
            confidence = 0.5
        else:
            confidence = min(0.95, 0.55 + best_score * 0.1)
        return TaxonomyResult(
            taxonomy=best.id,
            confidence=confidence,
            required_entities=best.required_entities,
            preferred_sources=best.preferred_sources,
            rights_threshold=best.rights_threshold,
            version=best.version,
            retrieval_policy=best.retrieval_policy,
        )


def load_taxonomy_definitions(path: Path) -> list[TaxonomyDefinition]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("taxonomy config must be a list")
    definitions: list[TaxonomyDefinition] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("taxonomy definitions must be objects")
        for key in ["id", "version", "keywords", "required_entities", "preferred_sources", "retrieval_policy"]:
            if key not in item:
                raise ValueError(f"taxonomy definition missing {key}")
        definitions.append(
            TaxonomyDefinition(
                id=str(item["id"]),
                version=str(item["version"]),
                keywords=tuple(str(value) for value in item["keywords"]),
                required_entities=tuple(str(value) for value in item["required_entities"]),
                preferred_sources=tuple(str(value) for value in item["preferred_sources"]),
                retrieval_policy=dict(item["retrieval_policy"]),
            )
        )
    if "general_concept" not in {definition.id for definition in definitions}:
        raise ValueError("taxonomy config must include general_concept fallback")
    return definitions
