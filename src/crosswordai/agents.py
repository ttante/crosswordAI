"""Bounded agentic critic workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter

from crosswordai.clues import ClueCandidate, ClueQualityGate, ClueRepairLoop


@dataclass(frozen=True, slots=True)
class AgentDecision:
    role: str
    status: str
    message: str
    iteration: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    tool_calls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentRoleSpec:
    role: str
    objective: str
    tool_allowlist: tuple[str, ...]
    can_override_hard_gates: bool = False


@dataclass(frozen=True, slots=True)
class AgentBudget:
    max_iterations: int = 2
    max_cost: float = 0.05
    max_latency_ms: float = 5000.0


@dataclass(frozen=True, slots=True)
class AgentWorkflowReport:
    final_clue: ClueCandidate
    decisions: tuple[AgentDecision, ...]
    disagreement_events: tuple[str, ...] = ()
    budget_exhausted: bool = False
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    role_specs: tuple[AgentRoleSpec, ...] = field(default_factory=tuple)


class ClueCriticWorkflow:
    """A bounded critic loop that cannot override deterministic quality gates."""

    DEFAULT_ROLES = (
        AgentRoleSpec("clue_writer", "Repair weak clue wording.", ("repair_clue",)),
        AgentRoleSpec("clue_critic", "Apply ambiguity, leakage, and style checks.", ("validate_clue",)),
        AgentRoleSpec("fact_checker", "Verify source support and evidence quotes.", ("validate_evidence",)),
        AgentRoleSpec("rights_reviewer", "Check rights risk gates.", ("validate_rights",)),
        AgentRoleSpec("puzzle_editor", "Record final editorial decision.", ("record_decision",)),
    )

    def __init__(
        self,
        *,
        max_iterations: int = 2,
        budget: AgentBudget | None = None,
        roles: tuple[AgentRoleSpec, ...] | None = None,
    ) -> None:
        self.budget = budget or AgentBudget(max_iterations=max_iterations)
        self.roles = roles or self.DEFAULT_ROLES
        self.quality_gate = ClueQualityGate()
        self.repair_loop = ClueRepairLoop(self.quality_gate, max_attempts=1)

    def run(self, clue: ClueCandidate) -> tuple[ClueCandidate, list[AgentDecision]]:
        report = self.run_report(clue)
        return report.final_clue, list(report.decisions)

    def run_report(self, clue: ClueCandidate) -> AgentWorkflowReport:
        start = perf_counter()
        decisions: list[AgentDecision] = []
        disagreements: list[str] = []
        current = clue
        total_cost = 0.0
        budget_exhausted = False
        for iteration in range(1, self.budget.max_iterations + 1):
            current = self.quality_gate.validate(current)
            critic_decision = _decision(
                role="clue_critic",
                status="accepted" if current.qa_status == "passed" else "rejected",
                message="Clue passed deterministic QA." if current.qa_status == "passed" else current.qa_status,
                iteration=iteration,
                tool_calls=("validate_clue",),
            )
            decisions.append(critic_decision)
            decisions.extend(self._specialist_decisions(current, iteration))
            total_cost += _iteration_cost(decisions[-3:])
            if current.qa_status == "passed":
                break
            if _latency_ms(start) > self.budget.max_latency_ms or total_cost >= self.budget.max_cost:
                budget_exhausted = True
                decisions.append(
                    _decision(
                        role="puzzle_editor",
                        status="budget_exhausted",
                        message="Repair loop stopped before deterministic gates passed.",
                        iteration=iteration,
                        tool_calls=("record_decision",),
                    )
                )
                break
            before_failures = current.qa_failures
            current = self.repair_loop.repair(current)
            if before_failures and current.qa_failures and before_failures != current.qa_failures:
                disagreements.append(f"repair_shifted_failures:{','.join(before_failures)}->{','.join(current.qa_failures)}")
        final = self.quality_gate.validate(current)
        if final.qa_status != "passed":
            decisions.append(
                _decision(
                    role="puzzle_editor",
                    status="quarantined",
                    message=final.qa_status,
                    iteration=self.budget.max_iterations,
                    tool_calls=("record_decision",),
                )
            )
        return AgentWorkflowReport(
            final_clue=final,
            decisions=tuple(decisions),
            disagreement_events=tuple(disagreements),
            budget_exhausted=budget_exhausted,
            total_cost=round(total_cost, 5),
            total_latency_ms=round(_latency_ms(start), 3),
            role_specs=self.roles,
        )

    def _specialist_decisions(self, clue: ClueCandidate, iteration: int) -> list[AgentDecision]:
        decisions = []
        fact_status = "accepted" if "missing_evidence" not in clue.qa_failures and "missing_evidence_quote" not in clue.qa_failures else "rejected"
        decisions.append(
            _decision(
                role="fact_checker",
                status=fact_status,
                message="Evidence support checked.",
                iteration=iteration,
                tool_calls=("validate_evidence",),
            )
        )
        rights_status = "accepted" if "high_rights_risk" not in clue.qa_failures else "rejected"
        decisions.append(
            _decision(
                role="rights_reviewer",
                status=rights_status,
                message="Rights risk checked.",
                iteration=iteration,
                tool_calls=("validate_rights",),
            )
        )
        return decisions

    def _repair(self, clue: ClueCandidate) -> ClueCandidate:
        return self.repair_loop.repair(clue)


def _decision(
    *,
    role: str,
    status: str,
    message: str,
    iteration: int,
    tool_calls: tuple[str, ...],
) -> AgentDecision:
    return AgentDecision(
        role=role,
        status=status,
        message=message,
        iteration=iteration,
        cost=0.001,
        latency_ms=1.0,
        tool_calls=tool_calls,
    )


def _iteration_cost(decisions: list[AgentDecision]) -> float:
    return sum(decision.cost for decision in decisions)


def _latency_ms(start: float) -> float:
    return (perf_counter() - start) * 1000.0
