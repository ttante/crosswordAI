"""Export payloads for generated puzzle artifacts.

Exports are public-safe by default: they preserve lineage, source IDs, hashes,
and QA metadata while avoiding raw evidence quote leakage.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Any

from crosswordai.clues import ClueCandidate
from crosswordai.qa import PublishDecision
from crosswordai.solver import Grid, extract_entries


def puzzle_json(
    *,
    puzzle_id: str,
    grid: Grid,
    clues: list[ClueCandidate],
    publish_decision: PublishDecision,
    source_pack_id: str,
    public_safe: bool = True,
) -> dict[str, Any]:
    clue_payloads = [_safe_clue_payload(index, clue, include_answer=not public_safe) for index, clue in enumerate(clues, start=1)]
    return {
        "puzzle_id": puzzle_id,
        "source_pack_id": source_pack_id,
        "grid": {"width": grid.width, "height": grid.height, "rows": list(grid.rows)},
        "entries": extract_entries(grid),
        "clues": clue_payloads,
        "answer_key": answer_key_json(clues=clues),
        "publish_decision": publish_decision_json(publish_decision),
        "qa_scorecard": qa_scorecard_json(publish_decision),
        "source_map": source_map_json(source_pack_id=source_pack_id, clues=clues),
        "model_lineage": model_lineage_json(clues=clues),
        "export_policy": {
            "public_safe": public_safe,
            "raw_evidence_quotes_included": False,
            "copyright_sensitive_fields_removed": ["evidence_quotes"],
        },
    }


def answer_key_json(*, clues: list[ClueCandidate]) -> dict[str, Any]:
    return {
        "answers": [
            {
                "answer": clue.answer,
                "answer_hash": _hash(clue.answer),
                "enumeration": len(_normalize_answer(clue.answer)),
                "clue_id": f"clue_{index:03d}",
                "difficulty": clue.difficulty,
                "style": clue.clue_style,
            }
            for index, clue in enumerate(clues, start=1)
        ]
    }


def source_map_json(*, source_pack_id: str, clues: list[ClueCandidate]) -> dict[str, Any]:
    evidence_refs: dict[str, dict[str, Any]] = {}
    for index, clue in enumerate(clues, start=1):
        for evidence_id in clue.source_evidence_ids:
            ref = evidence_refs.setdefault(
                evidence_id,
                {
                    "evidence_id": evidence_id,
                    "source_pack_id": source_pack_id,
                    "clue_ids": [],
                    "answer_hashes": [],
                    "rights_risk": clue.rights_risk,
                    "raw_text_included": False,
                },
            )
            ref["clue_ids"].append(f"clue_{index:03d}")
            ref["answer_hashes"].append(_hash(clue.answer))
            ref["rights_risk"] = _max_risk(str(ref["rights_risk"]), clue.rights_risk)
    return {
        "source_pack_id": source_pack_id,
        "evidence_refs": list(evidence_refs.values()),
    }


def qa_scorecard_json(publish_decision: PublishDecision) -> dict[str, Any]:
    scorecard = publish_decision.scorecard
    return {
        "passed": scorecard.passed,
        "hard_gate_failures": list(scorecard.hard_gate_failures),
        "soft_score": scorecard.soft_score,
        "metrics": dict(scorecard.metrics),
        "clue_results": [asdict(result) for result in scorecard.clue_results],
    }


def model_lineage_json(*, clues: list[ClueCandidate], run_id: str | None = None) -> dict[str, Any]:
    lineage: dict[str, dict[str, Any]] = {}
    for clue in clues:
        for model_id in clue.model_lineage:
            item = lineage.setdefault(
                model_id,
                {
                    "model_id": model_id,
                    "run_id": run_id,
                    "prompt_ids": set(),
                    "schema_versions": set(),
                    "clue_count": 0,
                },
            )
            item["prompt_ids"].add(clue.prompt_id)
            item["schema_versions"].add(clue.schema_version)
            item["clue_count"] += 1
    return {
        "models": [
            {
                **item,
                "prompt_ids": sorted(item["prompt_ids"]),
                "schema_versions": sorted(item["schema_versions"]),
            }
            for item in lineage.values()
        ]
    }


def publish_decision_json(publish_decision: PublishDecision) -> dict[str, Any]:
    return {
        "status": publish_decision.status,
        "reasons": list(publish_decision.reasons),
        "soft_score": publish_decision.scorecard.soft_score,
    }


def export_bundle(
    *,
    puzzle_id: str,
    grid: Grid,
    clues: list[ClueCandidate],
    publish_decision: PublishDecision,
    source_pack_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    public_puzzle = None
    if publish_decision.status == "published" and publish_decision.scorecard.passed:
        public_puzzle = puzzle_json(
            puzzle_id=puzzle_id,
            grid=grid,
            clues=clues,
            publish_decision=publish_decision,
            source_pack_id=source_pack_id,
            public_safe=True,
        )
    return {
        "puzzle_id": puzzle_id,
        "source_pack_id": source_pack_id,
        "run_id": run_id,
        "status": publish_decision.status,
        "quarantine_reasons": list(publish_decision.reasons),
        "artifacts": {
            "public_puzzle": public_puzzle,
            "answer_key": answer_key_json(clues=clues),
            "source_map": source_map_json(source_pack_id=source_pack_id, clues=clues),
            "qa_scorecard": qa_scorecard_json(publish_decision),
            "model_lineage": model_lineage_json(clues=clues, run_id=run_id),
        },
        "hard_gate_enforced": publish_decision.status != "published" or publish_decision.scorecard.passed,
    }


def _safe_clue_payload(index: int, clue: ClueCandidate, *, include_answer: bool) -> dict[str, Any]:
    payload = {
        "clue_id": f"clue_{index:03d}",
        "clue_text": clue.clue_text,
        "clue_style": clue.clue_style,
        "difficulty": clue.difficulty,
        "clue_angle": clue.clue_angle,
        "source_evidence_ids": list(clue.source_evidence_ids),
        "fact_confidence": clue.fact_confidence,
        "ambiguity_score": clue.ambiguity_score,
        "rights_risk": clue.rights_risk,
        "qa_status": clue.qa_status,
        "qa_failures": list(clue.qa_failures),
        "model_lineage": list(clue.model_lineage),
        "prompt_id": clue.prompt_id,
        "schema_version": clue.schema_version,
        "answer_hash": _hash(clue.answer),
    }
    if include_answer:
        payload["answer"] = clue.answer
    return payload


def _hash(text: str) -> str:
    return hashlib.sha256(_normalize_answer(text).encode("utf-8")).hexdigest()[:16]


def _normalize_answer(text: str) -> str:
    return "".join(char for char in text.upper() if char.isalnum())


def _max_risk(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right
