"""Batch generation, checkpoints, and local execution primitives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from crosswordai.ids import utc_now_iso
from crosswordai.storage import ArtifactRecord, ArtifactStore


@dataclass(frozen=True, slots=True)
class BatchItem:
    theme: str
    route_id: str
    status: str = "pending"
    output_ref: str | None = None
    failure_reason: str | None = None
    item_id: str = ""
    checkpoint_ref: str | None = None
    estimated_cost: float = 0.0
    attempts: int = 0
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True, slots=True)
class BatchCheckpoint:
    run_set_id: str
    item_id: str
    status: str
    output_ref: str | None
    failure_reason: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class BatchExecutionPolicy:
    max_items: int | None = None
    max_cost: float | None = None
    cancel_after: int | None = None
    max_attempts: int = 1


@dataclass(frozen=True, slots=True)
class BatchExecutionReport:
    run_set_id: str
    summary: dict[str, int]
    total_cost: float
    checkpoint_refs: tuple[str, ...]
    stopped_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BatchInspectionReport:
    run_set_id: str
    created_at: str
    summary: dict[str, int]
    reproducibility_hash: str
    outputs: tuple[str, ...]
    failures: tuple[str, ...]


class BatchItemHandler(Protocol):
    def __call__(self, item: BatchItem) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class BatchRunSet:
    id: str
    created_at: str
    items: list[BatchItem] = field(default_factory=list)

    @classmethod
    def create(cls, id: str, themes: list[str], routes: list[str]) -> "BatchRunSet":
        items = [
            BatchItem(theme, route, item_id=_item_id(id, theme, route, index))
            for index, (theme, route) in enumerate((theme, route) for theme in themes for route in routes)
        ]
        return cls(id=id, created_at=utc_now_iso(), items=items)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_set_id": self.id,
            "created_at": self.created_at,
            "items": [asdict(item) for item in self.items],
            "summary": self.summary(),
            "reproducibility": reproducibility_report(self),
        }


class LocalBatchExecutor:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        *,
        item_handler: BatchItemHandler | None = None,
        policy: BatchExecutionPolicy | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.item_handler = item_handler or default_batch_item_handler
        self.policy = policy or BatchExecutionPolicy()

    def execute(self, run_set: BatchRunSet) -> BatchExecutionReport:
        updated: list[BatchItem] = []
        checkpoints: list[str] = []
        total_cost = 0.0
        completed_count = 0
        stopped_reason: str | None = None
        for item in run_set.items:
            if item.status not in {"pending", "retry"}:
                updated.append(item)
                continue
            if self.policy.max_items is not None and completed_count >= self.policy.max_items:
                updated.append(_replace_item(item, status="skipped", failure_reason="max_items_reached"))
                stopped_reason = stopped_reason or "max_items_reached"
                continue
            if self.policy.cancel_after is not None and completed_count >= self.policy.cancel_after:
                updated.append(_replace_item(item, status="cancelled", failure_reason="cancelled_by_policy"))
                stopped_reason = stopped_reason or "cancelled_by_policy"
                continue
            if self.policy.max_cost is not None and total_cost >= self.policy.max_cost:
                updated.append(_replace_item(item, status="skipped", failure_reason="budget_exhausted"))
                stopped_reason = stopped_reason or "budget_exhausted"
                continue
            result_item, checkpoint = self._execute_item(run_set.id, item)
            total_cost += result_item.estimated_cost
            completed_count += 1
            checkpoints.append(checkpoint.output_ref or "")
            updated.append(result_item)
        run_set.items = updated
        return BatchExecutionReport(
            run_set_id=run_set.id,
            summary=run_set.summary(),
            total_cost=round(total_cost, 6),
            checkpoint_refs=tuple(ref for ref in checkpoints if ref),
            stopped_reason=stopped_reason,
        )

    def _execute_item(self, run_set_id: str, item: BatchItem) -> tuple[BatchItem, BatchCheckpoint]:
        started_at = utc_now_iso()
        attempts = item.attempts
        last_failure: str | None = None
        while attempts < self.policy.max_attempts:
            attempts += 1
            try:
                payload = self.item_handler(_replace_item(item, status="running", attempts=attempts, started_at=started_at))
                artifact = self.artifact_store.write_json(
                    {
                        "run_set_id": run_set_id,
                        "item_id": item.item_id,
                        "theme": item.theme,
                        "route_id": item.route_id,
                        "payload": payload,
                    },
                    media_type="application/vnd.crosswordai.batch-item-output+json",
                )
                completed = _replace_item(
                    item,
                    status=str(payload.get("status", "succeeded")),
                    output_ref=str(artifact.path),
                    estimated_cost=float(payload.get("estimated_cost", 0.0)),
                    attempts=attempts,
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                )
                checkpoint = self._checkpoint(run_set_id, completed, artifact)
                return _replace_item(completed, checkpoint_ref=checkpoint.output_ref), checkpoint
            except Exception as exc:  # noqa: BLE001 - batch engine records item failures.
                last_failure = str(exc)
        failed = _replace_item(
            item,
            status="failed",
            failure_reason=last_failure or "unknown_failure",
            attempts=attempts,
            started_at=started_at,
            completed_at=utc_now_iso(),
        )
        checkpoint = self._checkpoint(run_set_id, failed, None)
        return _replace_item(failed, checkpoint_ref=checkpoint.output_ref), checkpoint

    def _checkpoint(
        self,
        run_set_id: str,
        item: BatchItem,
        output: ArtifactRecord | None,
    ) -> BatchCheckpoint:
        checkpoint = BatchCheckpoint(
            run_set_id=run_set_id,
            item_id=item.item_id,
            status=item.status,
            output_ref=str(output.path) if output is not None else item.output_ref,
            failure_reason=item.failure_reason,
            created_at=utc_now_iso(),
        )
        artifact = self.artifact_store.write_json(
            asdict(checkpoint),
            media_type="application/vnd.crosswordai.batch-checkpoint+json",
        )
        return BatchCheckpoint(
            run_set_id=checkpoint.run_set_id,
            item_id=checkpoint.item_id,
            status=checkpoint.status,
            output_ref=str(artifact.path),
            failure_reason=checkpoint.failure_reason,
            created_at=checkpoint.created_at,
        )


def default_batch_item_handler(item: BatchItem) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "theme": item.theme,
        "route_id": item.route_id,
        "estimated_cost": _estimated_item_cost(item),
        "reproducibility_hash": _hash_json({"theme": item.theme, "route_id": item.route_id}),
    }


def inspect_batch_run_set(run_set: BatchRunSet) -> BatchInspectionReport:
    failures = tuple(f"{item.item_id}:{item.failure_reason}" for item in run_set.items if item.failure_reason)
    outputs = tuple(item.output_ref for item in run_set.items if item.output_ref)
    return BatchInspectionReport(
        run_set_id=run_set.id,
        created_at=run_set.created_at,
        summary=run_set.summary(),
        reproducibility_hash=reproducibility_report(run_set)["hash"],
        outputs=outputs,
        failures=failures,
    )


def reproducibility_report(run_set: BatchRunSet) -> dict[str, Any]:
    payload = {
        "run_set_id": run_set.id,
        "items": [
            {
                "theme": item.theme,
                "route_id": item.route_id,
                "item_id": item.item_id,
            }
            for item in run_set.items
        ],
    }
    return {
        "hash": _hash_json(payload),
        "theme_count": len({item.theme for item in run_set.items}),
        "route_count": len({item.route_id for item in run_set.items}),
        "item_count": len(run_set.items),
    }


def _replace_item(item: BatchItem, **changes: Any) -> BatchItem:
    values = asdict(item)
    values.update(changes)
    return BatchItem(**values)


def _item_id(run_set_id: str, theme: str, route_id: str, index: int) -> str:
    return "bi_" + _hash_json({"run_set_id": run_set_id, "theme": theme, "route_id": route_id, "index": index})[:16]


def _estimated_item_cost(item: BatchItem) -> float:
    return round(0.01 + len(item.theme.split()) * 0.002 + len(item.route_id) * 0.0001, 6)


def _hash_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
