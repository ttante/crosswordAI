"""Local workflow execution with idempotent stage checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StageResult:
    name: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None


class Stage(Protocol):
    name: str

    def run(self, context: dict[str, Any]) -> StageResult:
        ...


class LocalWorkflowExecutor:
    def __init__(self) -> None:
        self.checkpoints: dict[str, StageResult] = {}

    def run(self, stages: list[Stage], context: dict[str, Any] | None = None) -> list[StageResult]:
        context = dict(context or {})
        results: list[StageResult] = []
        for stage in stages:
            if stage.name in self.checkpoints:
                result = self.checkpoints[stage.name]
            else:
                result = stage.run(context)
                self.checkpoints[stage.name] = result
            results.append(result)
            if result.status != "succeeded":
                break
            context.update(result.output)
        return results
