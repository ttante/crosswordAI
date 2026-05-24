"""Retrieval evaluation metrics, suites, and regression gates."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from crosswordai.vectors import SearchResult


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    query: str
    relevant_ids: tuple[str, ...]
    taxonomy: str = "general_concept"
    source_pack_id: str = ""
    required_source_types: tuple[str, ...] = ()
    min_recall_at_k: float = 1.0
    min_evidence_precision: float = 1.0
    max_stale_source_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class RetrievalEvalSuite:
    id: str
    version: str
    protected: bool
    cases: tuple[RetrievalEvalCase, ...]


@dataclass(frozen=True, slots=True)
class RetrievalEvalResult:
    recall_at_k: float
    evidence_precision: float
    source_diversity: int = 0
    stale_source_rate: float = 0.0
    no_result_rate: float = 0.0
    passed: bool = True
    failure_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalSuiteResult:
    suite_id: str
    version: str
    protected: bool
    case_results: tuple[RetrievalEvalResult, ...]
    passed: bool
    failure_clusters: dict[str, int]


def load_retrieval_eval_suite(path: Path) -> RetrievalEvalSuite:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in ["id", "version", "protected", "cases"]:
        if key not in raw:
            raise ValueError(f"retrieval eval suite missing {key}")
    cases = []
    for item in raw["cases"]:
        for key in ["query", "relevant_ids"]:
            if key not in item:
                raise ValueError(f"retrieval eval case missing {key}")
        cases.append(
            RetrievalEvalCase(
                query=str(item["query"]),
                relevant_ids=tuple(str(value) for value in item["relevant_ids"]),
                taxonomy=str(item.get("taxonomy", "general_concept")),
                source_pack_id=str(item.get("source_pack_id", "")),
                required_source_types=tuple(str(value) for value in item.get("required_source_types", [])),
                min_recall_at_k=float(item.get("min_recall_at_k", 1.0)),
                min_evidence_precision=float(item.get("min_evidence_precision", 1.0)),
                max_stale_source_rate=float(item.get("max_stale_source_rate", 0.0)),
            )
        )
    return RetrievalEvalSuite(
        id=str(raw["id"]),
        version=str(raw["version"]),
        protected=bool(raw["protected"]),
        cases=tuple(cases),
    )


def evaluate_results(results: list[SearchResult], case: RetrievalEvalCase, *, k: int) -> RetrievalEvalResult:
    top = results[:k]
    relevant = set(case.relevant_ids)
    returned = {result.id for result in top}
    recall = len(returned & relevant) / len(relevant) if relevant else 1.0
    precision = len(returned & relevant) / len(returned) if returned else 0.0
    source_types = {result.metadata.get("source_type", "") for result in top if result.metadata.get("source_type")}
    stale_count = sum(1 for result in top if result.metadata.get("stale") == "true")
    stale_rate = stale_count / len(top) if top else 0.0
    no_result_rate = 1.0 if not top else 0.0
    failures: list[str] = []
    if not top:
        failures.append("no_results")
    if recall < case.min_recall_at_k:
        failures.append("low_recall")
    if precision < case.min_evidence_precision:
        failures.append("low_precision")
    if stale_rate > case.max_stale_source_rate:
        failures.append("stale_sources")
    missing_source_types = set(case.required_source_types) - source_types
    if missing_source_types:
        failures.append("missing_source_type")
    return RetrievalEvalResult(
        recall_at_k=recall,
        evidence_precision=precision,
        source_diversity=len(source_types),
        stale_source_rate=stale_rate,
        no_result_rate=no_result_rate,
        passed=not failures,
        failure_reasons=tuple(failures),
    )


def evaluate_suite(
    suite: RetrievalEvalSuite,
    search_results_by_query: dict[str, list[SearchResult]],
    *,
    k: int,
) -> RetrievalSuiteResult:
    results = tuple(
        evaluate_results(search_results_by_query.get(case.query, []), case, k=k)
        for case in suite.cases
    )
    clusters = cluster_failures(results)
    return RetrievalSuiteResult(
        suite_id=suite.id,
        version=suite.version,
        protected=suite.protected,
        case_results=results,
        passed=all(result.passed for result in results),
        failure_clusters=clusters,
    )


def cluster_failures(results: tuple[RetrievalEvalResult, ...] | list[RetrievalEvalResult]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for result in results:
        counter.update(result.failure_reasons)
    return dict(counter)


def suite_result_to_dict(result: RetrievalSuiteResult) -> dict[str, object]:
    return {
        "suite_id": result.suite_id,
        "version": result.version,
        "protected": result.protected,
        "passed": result.passed,
        "failure_clusters": result.failure_clusters,
        "case_results": [
            {
                "recall_at_k": case.recall_at_k,
                "evidence_precision": case.evidence_precision,
                "source_diversity": case.source_diversity,
                "stale_source_rate": case.stale_source_rate,
                "no_result_rate": case.no_result_rate,
                "passed": case.passed,
                "failure_reasons": list(case.failure_reasons),
            }
            for case in result.case_results
        ],
    }
