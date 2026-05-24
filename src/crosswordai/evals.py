"""Evaluation registry, golden sets, and route comparison."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    taxonomy: str
    input_ref: str
    expected: dict[str, str]
    category: str = "golden"
    adversarial_tags: tuple[str, ...] = ()
    protected: bool = True


@dataclass(frozen=True, slots=True)
class GoldenSourcePack:
    id: str
    taxonomy: str
    theme: str
    artifact_ref: str
    content_hash: str
    frozen_at: str
    protected: bool = True


@dataclass(frozen=True, slots=True)
class EvalSuite:
    id: str
    version: str
    cases: tuple[EvalCase, ...]
    protected: bool = True
    golden_source_packs: tuple[GoldenSourcePack, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteScore:
    route_id: str
    quality: float
    cost: float
    latency_ms: float
    publish_rate: float

    @property
    def quality_per_dollar(self) -> float:
        return self.quality / max(self.cost, 0.01)


@dataclass(frozen=True, slots=True)
class EvalRunResult:
    route_id: str
    suite_id: str
    quality: float
    case_count: int
    passed_count: int
    failures: tuple[str, ...]
    protected_regressions: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures and self.protected_regressions == 0


@dataclass(frozen=True, slots=True)
class RouteComparison:
    baseline_route_id: str
    candidate_route_id: str
    quality_delta: float
    protected_regressions: int
    winner: str
    promotion_safe: bool


class ProtectedRegressionError(AssertionError):
    pass


class EvalRegistry:
    def __init__(self, suites: tuple[EvalSuite, ...] = ()) -> None:
        self._suites = {suite.id: suite for suite in suites}

    def register(self, suite: EvalSuite) -> None:
        self._suites[suite.id] = suite

    def get(self, suite_id: str) -> EvalSuite:
        return self._suites[suite_id]

    def list(self, *, taxonomy: str | None = None, protected: bool | None = None) -> list[EvalSuite]:
        suites = list(self._suites.values())
        if taxonomy is not None:
            suites = [suite for suite in suites if any(case.taxonomy == taxonomy for case in suite.cases)]
        if protected is not None:
            suites = [suite for suite in suites if suite.protected is protected]
        return sorted(suites, key=lambda suite: suite.id)

    @classmethod
    def load(cls, path: Path) -> "EvalRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        suites = tuple(_suite_from_dict(item) for item in payload.get("suites", []))
        return cls(suites)

    def to_dict(self) -> dict[str, Any]:
        return {"suites": [_suite_to_dict(suite) for suite in self.list()]}


def compare_routes(scores: list[RouteScore]) -> list[RouteScore]:
    return sorted(scores, key=lambda score: (score.quality_per_dollar, score.publish_rate), reverse=True)


def evaluate_route_outputs(
    *,
    route_id: str,
    suite: EvalSuite,
    outputs: dict[str, dict[str, str]],
) -> EvalRunResult:
    failures: list[str] = []
    protected_regressions = 0
    passed_count = 0
    for case in suite.cases:
        output = outputs.get(case.id, {})
        case_failures = _case_failures(case, output)
        if case_failures:
            failures.extend(f"{case.id}:{failure}" for failure in case_failures)
            if suite.protected and case.protected:
                protected_regressions += 1
            continue
        passed_count += 1
    quality = round(passed_count / len(suite.cases), 3) if suite.cases else 0.0
    return EvalRunResult(
        route_id=route_id,
        suite_id=suite.id,
        quality=quality,
        case_count=len(suite.cases),
        passed_count=passed_count,
        failures=tuple(failures),
        protected_regressions=protected_regressions,
        metrics={
            "publish_gate_regressions": float(protected_regressions),
            "failure_rate": round(1.0 - quality, 3),
        },
    )


def compare_eval_runs(*, baseline: EvalRunResult, candidate: EvalRunResult) -> RouteComparison:
    if baseline.suite_id != candidate.suite_id:
        raise ValueError("cannot compare eval runs from different suites")
    quality_delta = round(candidate.quality - baseline.quality, 3)
    promotion_safe = candidate.protected_regressions == 0 and quality_delta >= 0
    winner = candidate.route_id if quality_delta >= 0 and candidate.protected_regressions == 0 else baseline.route_id
    return RouteComparison(
        baseline_route_id=baseline.route_id,
        candidate_route_id=candidate.route_id,
        quality_delta=quality_delta,
        protected_regressions=candidate.protected_regressions,
        winner=winner,
        promotion_safe=promotion_safe,
    )


def assert_no_protected_regressions(result: EvalRunResult) -> None:
    if result.protected_regressions:
        raise ProtectedRegressionError(
            f"{result.route_id} produced {result.protected_regressions} protected regressions on {result.suite_id}"
        )


def build_adversarial_suite(*, suite_id: str = "adversarial-safety-v1") -> EvalSuite:
    cases = (
        EvalCase(
            "prompt_injection_clue",
            "general_concept",
            "fixture://adversarial/prompt-injection",
            {"status": "quarantined"},
            category="adversarial",
            adversarial_tags=("injection",),
        ),
        EvalCase(
            "misinformation_source",
            "media",
            "fixture://adversarial/misinformation",
            {"status": "quarantined"},
            category="adversarial",
            adversarial_tags=("misinformation",),
        ),
        EvalCase(
            "ambiguous_clue",
            "general_concept",
            "fixture://adversarial/ambiguity",
            {"qa_status": "failed"},
            category="adversarial",
            adversarial_tags=("ambiguity",),
        ),
        EvalCase(
            "rights_leakage",
            "music_artist",
            "fixture://adversarial/lyrics",
            {"raw_evidence_quotes_included": "false"},
            category="adversarial",
            adversarial_tags=("rights_leakage",),
        ),
        EvalCase(
            "offensive_fill",
            "general_concept",
            "fixture://adversarial/offensive-fill",
            {"status": "quarantined"},
            category="adversarial",
            adversarial_tags=("offensive_fill",),
        ),
    )
    return EvalSuite(suite_id, "1", cases, protected=True, metadata={"purpose": "hard-gate regression protection"})


def _case_failures(case: EvalCase, output: dict[str, str]) -> list[str]:
    failures = []
    for key, expected_value in case.expected.items():
        actual = output.get(key)
        if actual != expected_value:
            failures.append(f"{key}_expected_{expected_value}_got_{actual}")
    return failures


def _suite_from_dict(item: dict[str, Any]) -> EvalSuite:
    return EvalSuite(
        id=str(item["id"]),
        version=str(item["version"]),
        protected=bool(item.get("protected", True)),
        cases=tuple(_case_from_dict(case) for case in item.get("cases", [])),
        golden_source_packs=tuple(_golden_from_dict(pack) for pack in item.get("golden_source_packs", [])),
        metadata={str(key): str(value) for key, value in item.get("metadata", {}).items()},
    )


def _case_from_dict(item: dict[str, Any]) -> EvalCase:
    return EvalCase(
        id=str(item["id"]),
        taxonomy=str(item["taxonomy"]),
        input_ref=str(item["input_ref"]),
        expected={str(key): str(value) for key, value in item.get("expected", {}).items()},
        category=str(item.get("category", "golden")),
        adversarial_tags=tuple(str(tag) for tag in item.get("adversarial_tags", [])),
        protected=bool(item.get("protected", True)),
    )


def _golden_from_dict(item: dict[str, Any]) -> GoldenSourcePack:
    return GoldenSourcePack(
        id=str(item["id"]),
        taxonomy=str(item["taxonomy"]),
        theme=str(item["theme"]),
        artifact_ref=str(item["artifact_ref"]),
        content_hash=str(item["content_hash"]),
        frozen_at=str(item["frozen_at"]),
        protected=bool(item.get("protected", True)),
    )


def _suite_to_dict(suite: EvalSuite) -> dict[str, Any]:
    return {
        "id": suite.id,
        "version": suite.version,
        "protected": suite.protected,
        "metadata": dict(suite.metadata),
        "cases": [asdict_case(case) for case in suite.cases],
        "golden_source_packs": [asdict(golden) for golden in suite.golden_source_packs],
    }


def asdict_case(case: EvalCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "taxonomy": case.taxonomy,
        "input_ref": case.input_ref,
        "expected": dict(case.expected),
        "category": case.category,
        "adversarial_tags": list(case.adversarial_tags),
        "protected": case.protected,
    }
