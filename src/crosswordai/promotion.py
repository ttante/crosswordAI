"""Model, prompt, route, and policy promotion gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from crosswordai.ids import utc_now_iso


@dataclass(frozen=True, slots=True)
class PromotionCandidate:
    artifact_type: str
    artifact_id: str
    baseline_id: str
    eval_ref: str
    protected_gate_regressions: int
    rollback_target: str
    shadow_report_ref: str | None = None
    requested_by: str = "system"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    status: str
    reasons: tuple[str, ...]
    audit_ref: str | None = None
    rollback_target: str | None = None


@dataclass(frozen=True, slots=True)
class RegistryMutation:
    registry_name: str
    artifact_id: str
    baseline_id: str
    action: str
    created_at: str


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    artifact_type: str
    promoted_artifact_id: str
    rollback_target: str
    registry_mutations: tuple[RegistryMutation, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class PromotionAuditRecord:
    id: str
    candidate: PromotionCandidate
    decision: PromotionDecision
    rollback_plan: RollbackPlan | None
    created_at: str


@dataclass(frozen=True, slots=True)
class PromotionReport:
    candidate: PromotionCandidate
    decision: PromotionDecision
    rollback_plan: RollbackPlan | None
    audit_record: PromotionAuditRecord
    evidence: dict[str, str]


class PromotionGate:
    def __init__(self, *, require_shadow_mode: bool = False) -> None:
        self.require_shadow_mode = require_shadow_mode

    def decide(self, candidate: PromotionCandidate) -> PromotionDecision:
        reasons: list[str] = []
        if not candidate.eval_ref:
            reasons.append("missing_eval_evidence")
        if candidate.protected_gate_regressions:
            reasons.append("protected_gate_regression")
        if not candidate.rollback_target:
            reasons.append("missing_rollback_target")
        if self.require_shadow_mode and candidate.artifact_type == "route" and not candidate.shadow_report_ref:
            reasons.append("missing_shadow_mode_report")
        return PromotionDecision(
            "approved" if not reasons else "rejected",
            tuple(reasons),
            rollback_target=candidate.rollback_target or None,
        )


class PromotionWorkflow:
    def __init__(self, *, gate: PromotionGate | None = None) -> None:
        self.gate = gate or PromotionGate(require_shadow_mode=True)

    def run(self, candidate: PromotionCandidate) -> PromotionReport:
        decision = self.gate.decide(candidate)
        rollback_plan = build_rollback_plan(candidate) if decision.status == "approved" else None
        audit_record = PromotionAuditRecord(
            id=_audit_id(candidate),
            candidate=candidate,
            decision=PromotionDecision(
                decision.status,
                decision.reasons,
                audit_ref=_audit_id(candidate),
                rollback_target=decision.rollback_target,
            ),
            rollback_plan=rollback_plan,
            created_at=utc_now_iso(),
        )
        return PromotionReport(
            candidate=candidate,
            decision=audit_record.decision,
            rollback_plan=rollback_plan,
            audit_record=audit_record,
            evidence=promotion_evidence(candidate),
        )


def build_rollback_plan(candidate: PromotionCandidate) -> RollbackPlan:
    mutation = RegistryMutation(
        registry_name=_registry_for(candidate.artifact_type),
        artifact_id=candidate.artifact_id,
        baseline_id=candidate.baseline_id,
        action="promote",
        created_at=utc_now_iso(),
    )
    rollback = RegistryMutation(
        registry_name=_registry_for(candidate.artifact_type),
        artifact_id=candidate.rollback_target,
        baseline_id=candidate.artifact_id,
        action="rollback",
        created_at=utc_now_iso(),
    )
    return RollbackPlan(
        artifact_type=candidate.artifact_type,
        promoted_artifact_id=candidate.artifact_id,
        rollback_target=candidate.rollback_target,
        registry_mutations=(mutation, rollback),
        created_at=utc_now_iso(),
    )


def promotion_evidence(candidate: PromotionCandidate) -> dict[str, str]:
    return {
        "artifact_type": candidate.artifact_type,
        "artifact_id": candidate.artifact_id,
        "baseline_id": candidate.baseline_id,
        "eval_ref": candidate.eval_ref,
        "shadow_report_ref": candidate.shadow_report_ref or "",
        "rollback_target": candidate.rollback_target,
    }


def promotion_report_payload(report: PromotionReport) -> dict[str, object]:
    return {
        "candidate": asdict(report.candidate),
        "decision": asdict(report.decision),
        "rollback_plan": asdict(report.rollback_plan) if report.rollback_plan else None,
        "audit_record": {
            "id": report.audit_record.id,
            "created_at": report.audit_record.created_at,
        },
        "evidence": report.evidence,
    }


def _registry_for(artifact_type: str) -> str:
    mapping = {
        "model": "models",
        "prompt": "prompts",
        "route": "routes",
        "retrieval_policy": "policies",
        "judge": "models",
    }
    return mapping.get(artifact_type, f"{artifact_type}s")


def _audit_id(candidate: PromotionCandidate) -> str:
    import hashlib

    digest = hashlib.sha256(
        f"{candidate.artifact_type}:{candidate.artifact_id}:{candidate.eval_ref}:{candidate.rollback_target}".encode("utf-8")
    ).hexdigest()
    return f"promo_{digest[:16]}"
