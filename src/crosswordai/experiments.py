"""Model bakeoff and experiment matrix execution."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from crosswordai.evals import RouteScore, compare_routes
from crosswordai.ids import utc_now_iso
from crosswordai.storage import ArtifactRecord, ArtifactStore


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    id: str
    model_id: str
    prompt_id: str
    route_id: str
    retrieval_strategy: str
    judge_model_id: str
    repair_strategy: str
    taxonomy: str = "general_concept"


@dataclass(frozen=True, slots=True)
class ExperimentMatrix:
    id: str
    variants: tuple[ExperimentVariant, ...]
    source_pack_refs: tuple[str, ...]
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_axes(
        cls,
        *,
        id: str,
        models: tuple[str, ...],
        prompts: tuple[str, ...],
        routes: tuple[str, ...],
        retrieval_strategies: tuple[str, ...],
        judge_models: tuple[str, ...],
        repair_strategies: tuple[str, ...],
        source_pack_refs: tuple[str, ...],
        taxonomy: str = "general_concept",
    ) -> "ExperimentMatrix":
        variants: list[ExperimentVariant] = []
        for model in models:
            for prompt in prompts:
                for route in routes:
                    for retrieval in retrieval_strategies:
                        for judge in judge_models:
                            for repair in repair_strategies:
                                variants.append(
                                    ExperimentVariant(
                                        id=_variant_id(model, prompt, route, retrieval, judge, repair, taxonomy),
                                        model_id=model,
                                        prompt_id=prompt,
                                        route_id=route,
                                        retrieval_strategy=retrieval,
                                        judge_model_id=judge,
                                        repair_strategy=repair,
                                        taxonomy=taxonomy,
                                    )
                                )
        return cls(id=id, variants=tuple(variants), source_pack_refs=source_pack_refs)


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    experiment_id: str
    variant_id: str
    route_score: RouteScore
    taxonomy: str
    source_pack_count: int
    failure_modes: tuple[str, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    experiment_id: str
    results: tuple[ExperimentResult, ...]
    leaderboard: tuple[RouteScore, ...]
    taxonomy_leaderboards: dict[str, tuple[RouteScore, ...]]
    winner_route_id: str | None
    artifact_ref: str | None = None


ExperimentEvaluator = Callable[[ExperimentVariant, tuple[str, ...]], ExperimentResult]


class ExperimentMatrixRunner:
    def __init__(
        self,
        *,
        evaluator: ExperimentEvaluator | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.evaluator = evaluator or deterministic_experiment_evaluator
        self.artifact_store = artifact_store

    def run(self, matrix: ExperimentMatrix) -> ExperimentReport:
        results = tuple(
            replace(self.evaluator(variant, matrix.source_pack_refs), experiment_id=matrix.id)
            for variant in matrix.variants
        )
        leaderboard = tuple(compare_routes([result.route_score for result in results]))
        taxonomy_leaderboards = leaderboard_by_taxonomy(results)
        artifact_ref = None
        if self.artifact_store is not None:
            artifact = self.artifact_store.write_json(
                experiment_report_payload(matrix=matrix, results=results, leaderboard=leaderboard),
                media_type="application/vnd.crosswordai.experiment-report+json",
            )
            artifact_ref = str(artifact.path)
        return ExperimentReport(
            experiment_id=matrix.id,
            results=results,
            leaderboard=leaderboard,
            taxonomy_leaderboards=taxonomy_leaderboards,
            winner_route_id=leaderboard[0].route_id if leaderboard else None,
            artifact_ref=artifact_ref,
        )


def deterministic_experiment_evaluator(
    variant: ExperimentVariant,
    source_pack_refs: tuple[str, ...],
) -> ExperimentResult:
    route_bonus = {
        "cheap_first_cascade": 0.05,
        "jury_review": 0.04,
        "debate_and_judge": 0.035,
        "self_play_solver": 0.03,
        "bandit_router": 0.025,
    }.get(variant.route_id, 0.0)
    quality = min(0.99, 0.72 + route_bonus + _stable_fraction(variant.id, 0.08))
    cost = round(0.05 + len(source_pack_refs) * 0.02 + _stable_fraction(variant.model_id, 0.05), 4)
    latency = round(250.0 + len(source_pack_refs) * 40.0 + _stable_fraction(variant.prompt_id, 120.0), 3)
    publish_rate = min(0.99, quality - 0.04 + _stable_fraction(variant.repair_strategy, 0.04))
    failures = _failure_modes(quality, cost, latency)
    return ExperimentResult(
        experiment_id="",
        variant_id=variant.id,
        taxonomy=variant.taxonomy,
        source_pack_count=len(source_pack_refs),
        route_score=RouteScore(
            route_id=variant.route_id,
            quality=round(quality, 3),
            cost=cost,
            latency_ms=latency,
            publish_rate=round(publish_rate, 3),
        ),
        failure_modes=failures,
        metrics={
            "quality": round(quality, 3),
            "cost": cost,
            "latency_ms": latency,
            "publish_rate": round(publish_rate, 3),
        },
    )


def leaderboard_by_taxonomy(results: tuple[ExperimentResult, ...]) -> dict[str, tuple[RouteScore, ...]]:
    grouped: dict[str, list[RouteScore]] = defaultdict(list)
    for result in results:
        grouped[result.taxonomy].append(result.route_score)
    return {taxonomy: tuple(compare_routes(scores)) for taxonomy, scores in grouped.items()}


def experiment_report_payload(
    *,
    matrix: ExperimentMatrix,
    results: tuple[ExperimentResult, ...],
    leaderboard: tuple[RouteScore, ...],
) -> dict[str, Any]:
    return {
        "experiment_id": matrix.id,
        "created_at": matrix.created_at,
        "source_pack_refs": list(matrix.source_pack_refs),
        "variant_count": len(matrix.variants),
        "variants": [asdict(variant) for variant in matrix.variants],
        "results": [asdict(result) for result in results],
        "leaderboard": [asdict(score) | {"quality_per_dollar": score.quality_per_dollar} for score in leaderboard],
        "winner_route_id": leaderboard[0].route_id if leaderboard else None,
    }


def persist_experiment_report(
    *,
    artifact_store: ArtifactStore,
    report: ExperimentReport,
) -> ArtifactRecord:
    return artifact_store.write_json(
        {
            "experiment_id": report.experiment_id,
            "results": [asdict(result) for result in report.results],
            "leaderboard": [asdict(score) | {"quality_per_dollar": score.quality_per_dollar} for score in report.leaderboard],
            "taxonomy_leaderboards": {
                taxonomy: [asdict(score) for score in scores]
                for taxonomy, scores in report.taxonomy_leaderboards.items()
            },
            "winner_route_id": report.winner_route_id,
        },
        media_type="application/vnd.crosswordai.experiment-report+json",
    )


def _variant_id(*parts: str) -> str:
    return "var_" + _hash_json({"parts": parts})[:16]


def _stable_fraction(text: str, scale: float) -> float:
    value = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
    return (value / 0xFFFFFFFF) * scale


def _hash_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _failure_modes(quality: float, cost: float, latency_ms: float) -> tuple[str, ...]:
    failures = []
    if quality < 0.75:
        failures.append("low_quality")
    if cost > 0.12:
        failures.append("high_cost")
    if latency_ms > 450:
        failures.append("high_latency")
    return tuple(failures)
