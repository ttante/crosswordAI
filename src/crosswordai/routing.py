"""Advanced model-routing strategy descriptors and local executors."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RouteStrategy:
    id: str
    kind: str
    description: str
    experimental: bool = True


@dataclass(frozen=True, slots=True)
class RouteOption:
    route_id: str
    quality: float
    cost: float
    latency_ms: float
    output: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    selected_route_id: str
    status: str
    reasons: tuple[str, ...]
    options: tuple[RouteOption, ...]
    shadow_results: tuple[RouteOption, ...] = ()
    promotion_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShadowModeReport:
    baseline_route_id: str
    candidate_route_id: str
    quality_delta: float
    cost_delta: float
    latency_delta_ms: float
    promote: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BanditArmState:
    route_id: str
    pulls: int = 0
    reward_sum: float = 0.0

    @property
    def average_reward(self) -> float:
        return self.reward_sum / max(1, self.pulls)


RouteRunner = Callable[[str, dict[str, Any]], RouteOption]


DEFAULT_ADVANCED_ROUTES = (
    RouteStrategy("cheap_first_cascade", "cascade", "Draft locally, escalate only failures."),
    RouteStrategy("jury_review", "jury", "Use multiple small judges and escalate disagreements."),
    RouteStrategy("debate_and_judge", "debate", "Compare proposals and adversarial critiques."),
    RouteStrategy("self_play_solver", "self_play", "Have model routes try to solve generated clues."),
    RouteStrategy("bandit_router", "bandit", "Learn task routing from quality, latency, and cost."),
)


class AdvancedRouteExecutor:
    def __init__(
        self,
        route_runner: RouteRunner | None = None,
        *,
        quality_threshold: float = 0.75,
        bandit_state: dict[str, BanditArmState] | None = None,
    ) -> None:
        self.route_runner = route_runner or deterministic_route_runner
        self.quality_threshold = quality_threshold
        self.bandit_state = bandit_state or {}

    def execute(
        self,
        strategy_id: str,
        payload: dict[str, Any],
        *,
        baseline_route_id: str = "baseline-local",
        candidate_route_ids: tuple[str, ...] = ("mock-local",),
    ) -> RouteDecision:
        strategy = strategy_by_id(strategy_id)
        if strategy.kind == "cascade":
            return self._cheap_first_cascade(payload, baseline_route_id, candidate_route_ids)
        if strategy.kind == "jury":
            return self._jury(payload, candidate_route_ids)
        if strategy.kind == "debate":
            return self._debate(payload, candidate_route_ids)
        if strategy.kind == "self_play":
            return self._self_play(payload, candidate_route_ids)
        if strategy.kind == "bandit":
            return self._bandit(payload, candidate_route_ids)
        raise ValueError(f"unsupported route strategy: {strategy_id}")

    def shadow(
        self,
        *,
        payload: dict[str, Any],
        baseline_route_id: str,
        candidate_route_id: str,
        min_quality_delta: float = 0.02,
    ) -> tuple[RouteDecision, ShadowModeReport]:
        baseline = self.route_runner(baseline_route_id, payload)
        candidate = self.route_runner(candidate_route_id, payload)
        quality_delta = round(candidate.quality - baseline.quality, 3)
        cost_delta = round(candidate.cost - baseline.cost, 6)
        latency_delta = round(candidate.latency_ms - baseline.latency_ms, 3)
        reasons = []
        if quality_delta < min_quality_delta:
            reasons.append("quality_delta_below_threshold")
        if candidate.cost > baseline.cost * 2:
            reasons.append("candidate_cost_too_high")
        promote = not reasons
        report = ShadowModeReport(
            baseline_route_id=baseline.route_id,
            candidate_route_id=candidate.route_id,
            quality_delta=quality_delta,
            cost_delta=cost_delta,
            latency_delta_ms=latency_delta,
            promote=promote,
            reasons=tuple(reasons),
        )
        decision = RouteDecision(
            selected_route_id=baseline.route_id,
            status="shadow_only",
            reasons=("baseline_preserved",),
            options=(baseline,),
            shadow_results=(candidate,),
            promotion_evidence=shadow_report_payload(report),
        )
        return decision, report

    def _cheap_first_cascade(
        self,
        payload: dict[str, Any],
        baseline_route_id: str,
        candidate_route_ids: tuple[str, ...],
    ) -> RouteDecision:
        options: list[RouteOption] = []
        for route_id in (baseline_route_id,) + candidate_route_ids:
            option = self.route_runner(route_id, payload)
            options.append(option)
            if option.quality >= self.quality_threshold:
                return RouteDecision(
                    selected_route_id=option.route_id,
                    status="selected",
                    reasons=("quality_threshold_met",),
                    options=tuple(options),
                    promotion_evidence=_promotion_evidence(tuple(options)),
                )
        best = max(options, key=lambda option: (option.quality, -option.cost))
        return RouteDecision(best.route_id, "selected", ("best_available_after_cascade",), tuple(options), promotion_evidence=_promotion_evidence(tuple(options)))

    def _jury(self, payload: dict[str, Any], candidate_route_ids: tuple[str, ...]) -> RouteDecision:
        options = tuple(self.route_runner(route_id, payload) for route_id in candidate_route_ids)
        grouped: dict[str, list[RouteOption]] = defaultdict(list)
        for option in options:
            grouped[str(option.output.get("answer", option.route_id))].append(option)
        winner_group = max(grouped.values(), key=lambda items: (len(items), sum(item.quality for item in items)))
        selected = max(winner_group, key=lambda item: (item.quality, -item.cost))
        reasons = ("jury_consensus",) if len(winner_group) > 1 else ("jury_no_consensus_quality_tiebreak",)
        return RouteDecision(selected.route_id, "selected", reasons, options, promotion_evidence=_promotion_evidence(options))

    def _debate(self, payload: dict[str, Any], candidate_route_ids: tuple[str, ...]) -> RouteDecision:
        options = tuple(self.route_runner(route_id, payload) for route_id in candidate_route_ids)
        selected = max(options, key=lambda option: (option.quality - option.cost * 0.1, -option.latency_ms))
        reasons = ("debate_score_winner",)
        return RouteDecision(selected.route_id, "selected", reasons, options, promotion_evidence=_promotion_evidence(options))

    def _self_play(self, payload: dict[str, Any], candidate_route_ids: tuple[str, ...]) -> RouteDecision:
        options = tuple(self.route_runner(route_id, payload) for route_id in candidate_route_ids)
        solvable = [option for option in options if bool(option.output.get("self_play_solved", option.quality >= self.quality_threshold))]
        selected = max(solvable or list(options), key=lambda option: (option.quality, -option.cost))
        reasons = ("self_play_solved",) if solvable else ("self_play_no_solver_success",)
        return RouteDecision(selected.route_id, "selected", reasons, options, promotion_evidence=_promotion_evidence(options))

    def _bandit(self, payload: dict[str, Any], candidate_route_ids: tuple[str, ...]) -> RouteDecision:
        for route_id in candidate_route_ids:
            self.bandit_state.setdefault(route_id, BanditArmState(route_id))
        selected_state = min(self.bandit_state.values(), key=lambda state: state.pulls)
        if selected_state.pulls > 0:
            selected_state = max(self.bandit_state.values(), key=lambda state: state.average_reward)
        option = self.route_runner(selected_state.route_id, payload)
        reward = option.quality - option.cost * 0.2 - option.latency_ms * 0.00001
        self.bandit_state[selected_state.route_id] = BanditArmState(
            route_id=selected_state.route_id,
            pulls=selected_state.pulls + 1,
            reward_sum=selected_state.reward_sum + reward,
        )
        return RouteDecision(
            selected_route_id=option.route_id,
            status="selected",
            reasons=("bandit_reward_policy",),
            options=(option,),
            promotion_evidence={
                "bandit_state": {
                    route_id: {"pulls": state.pulls, "average_reward": state.average_reward}
                    for route_id, state in self.bandit_state.items()
                }
            },
        )


def strategy_by_id(strategy_id: str) -> RouteStrategy:
    for strategy in DEFAULT_ADVANCED_ROUTES:
        if strategy.id == strategy_id:
            return strategy
    raise KeyError(strategy_id)


def deterministic_route_runner(route_id: str, payload: dict[str, Any]) -> RouteOption:
    text = route_id + str(sorted(payload.items()))
    quality = 0.68 + (_stable_value(text, 0.22))
    if route_id in {"baseline-local", "mock-local"}:
        quality += 0.03
    cost = 0.01 + len(route_id) * 0.001 + _stable_value(route_id, 0.02)
    latency_ms = 120.0 + len(route_id) * 7.0 + _stable_value(text + "latency", 80.0)
    return RouteOption(
        route_id=route_id,
        quality=round(min(0.99, quality), 3),
        cost=round(cost, 6),
        latency_ms=round(latency_ms, 3),
        output={
            "answer": payload.get("answer", "candidate"),
            "self_play_solved": quality >= 0.76,
        },
    )


def shadow_report_payload(report: ShadowModeReport) -> dict[str, Any]:
    return {
        "baseline_route_id": report.baseline_route_id,
        "candidate_route_id": report.candidate_route_id,
        "quality_delta": report.quality_delta,
        "cost_delta": report.cost_delta,
        "latency_delta_ms": report.latency_delta_ms,
        "promote": report.promote,
        "reasons": list(report.reasons),
    }


def _promotion_evidence(options: tuple[RouteOption, ...]) -> dict[str, Any]:
    best = max(options, key=lambda option: (option.quality, -option.cost)) if options else None
    return {
        "option_count": len(options),
        "best_route_id": best.route_id if best else None,
        "best_quality": best.quality if best else 0.0,
        "routes": [
            {
                "route_id": option.route_id,
                "quality": option.quality,
                "cost": option.cost,
                "latency_ms": option.latency_ms,
            }
            for option in options
        ],
    }


def _stable_value(text: str, scale: float) -> float:
    import hashlib

    value = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
    return (value / 0xFFFFFFFF) * scale
