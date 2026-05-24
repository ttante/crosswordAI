"""Distributed batch and GPU-throughput execution seams."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any

from crosswordai.ids import utc_now_iso


@dataclass(frozen=True, slots=True)
class GPUBatchingConfig:
    enabled: bool = False
    max_batch_size: int = 1
    target_device: str = "cpu"
    precision: str = "fp32"


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    id: str
    task_types: tuple[str, ...]
    max_concurrency: int = 1
    gpu: GPUBatchingConfig = field(default_factory=GPUBatchingConfig)


@dataclass(frozen=True, slots=True)
class WorkerHealth:
    worker_id: str
    status: str
    active_tasks: int
    completed_tasks: int
    failed_tasks: int
    last_heartbeat_at: str


@dataclass(frozen=True, slots=True)
class DistributedTask:
    id: str
    task_type: str
    payload: dict[str, Any]
    max_retries: int = 1


@dataclass(frozen=True, slots=True)
class DistributedTaskResult:
    task_id: str
    worker_id: str
    status: str
    output: dict[str, Any]
    retry_count: int
    latency_ms: float
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ThroughputBenchmark:
    task_count: int
    succeeded: int
    failed: int
    total_latency_ms: float
    tasks_per_second: float
    worker_health: tuple[WorkerHealth, ...]
    gpu_config: GPUBatchingConfig


TaskHandler = Callable[[DistributedTask], dict[str, Any]]


class LocalDistributedExecutor:
    def __init__(
        self,
        workers: tuple[WorkerSpec, ...],
        *,
        handlers: dict[str, TaskHandler] | None = None,
    ) -> None:
        if not workers:
            raise ValueError("at least one worker is required")
        self.workers = workers
        self.handlers = handlers or {}
        self._completed: dict[str, int] = {worker.id: 0 for worker in workers}
        self._failed: dict[str, int] = {worker.id: 0 for worker in workers}

    def execute(self, tasks: tuple[DistributedTask, ...]) -> tuple[DistributedTaskResult, ...]:
        results: list[DistributedTaskResult] = []
        for task in tasks:
            worker = self._worker_for(task)
            result = self._execute_task(task, worker)
            if result.status == "succeeded":
                self._completed[worker.id] += 1
            else:
                self._failed[worker.id] += 1
            results.append(result)
        return tuple(results)

    def benchmark(self, tasks: tuple[DistributedTask, ...]) -> ThroughputBenchmark:
        started = perf_counter()
        results = self.execute(tasks)
        total_latency_ms = (perf_counter() - started) * 1000.0
        succeeded = sum(1 for result in results if result.status == "succeeded")
        failed = len(results) - succeeded
        gpu_config = self.workers[0].gpu
        return ThroughputBenchmark(
            task_count=len(tasks),
            succeeded=succeeded,
            failed=failed,
            total_latency_ms=round(total_latency_ms, 3),
            tasks_per_second=round(len(tasks) / max(total_latency_ms / 1000.0, 0.001), 3),
            worker_health=self.health(),
            gpu_config=gpu_config,
        )

    def health(self) -> tuple[WorkerHealth, ...]:
        return tuple(
            WorkerHealth(
                worker_id=worker.id,
                status="healthy",
                active_tasks=0,
                completed_tasks=self._completed[worker.id],
                failed_tasks=self._failed[worker.id],
                last_heartbeat_at=utc_now_iso(),
            )
            for worker in self.workers
        )

    def _worker_for(self, task: DistributedTask) -> WorkerSpec:
        for worker in self.workers:
            if task.task_type in worker.task_types:
                return worker
        raise ValueError(f"no worker supports task type: {task.task_type}")

    def _execute_task(self, task: DistributedTask, worker: WorkerSpec) -> DistributedTaskResult:
        retry_count = 0
        started = perf_counter()
        last_failure: str | None = None
        while retry_count <= task.max_retries:
            try:
                handler = self.handlers.get(task.task_type, default_distributed_handler)
                output = handler(task)
                return DistributedTaskResult(
                    task_id=task.id,
                    worker_id=worker.id,
                    status=str(output.get("status", "succeeded")),
                    output=output,
                    retry_count=retry_count,
                    latency_ms=round((perf_counter() - started) * 1000.0, 3),
                )
            except Exception as exc:  # noqa: BLE001 - distributed task failures are recorded.
                last_failure = str(exc)
                retry_count += 1
        return DistributedTaskResult(
            task_id=task.id,
            worker_id=worker.id,
            status="failed",
            output={},
            retry_count=max(0, retry_count - 1),
            latency_ms=round((perf_counter() - started) * 1000.0, 3),
            failure_reason=last_failure,
        )


class RayDistributedExecutor:
    """Ray adapter seam.

    The local executor is used in tests and development. This adapter keeps the
    production shape explicit without requiring Ray in the base install.
    """

    def __init__(self) -> None:
        try:
            import ray  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("RayDistributedExecutor requires the optional 'ray' package.") from exc
        self.ray = ray


def default_distributed_handler(task: DistributedTask) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "task_type": task.task_type,
        "payload_keys": sorted(task.payload.keys()),
    }


def throughput_report_payload(benchmark: ThroughputBenchmark) -> dict[str, Any]:
    return {
        "task_count": benchmark.task_count,
        "succeeded": benchmark.succeeded,
        "failed": benchmark.failed,
        "total_latency_ms": benchmark.total_latency_ms,
        "tasks_per_second": benchmark.tasks_per_second,
        "worker_health": [asdict(health) for health in benchmark.worker_health],
        "gpu_config": asdict(benchmark.gpu_config),
    }
