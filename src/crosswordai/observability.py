"""OpenTelemetry-shaped local tracing and LLMOps rollups."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Iterator, Protocol
from urllib.request import Request, urlopen

from crosswordai.ids import utc_now_iso
from crosswordai.qa import PublishDecision


@dataclass(frozen=True, slots=True)
class Span:
    name: str
    started_at: str
    duration_ms: float
    attributes: dict[str, str] = field(default_factory=dict)
    status: str = "ok"
    events: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMOpsRollup:
    total_cost: float
    total_latency_ms: float
    retry_count: int
    cache_hit_rate: float
    model_call_count: int
    retrieval_call_count: int
    validator_count: int
    export_count: int
    qa_gate_failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunInspectionReport:
    run_id: str
    run: dict[str, Any] | None
    artifacts: list[dict[str, Any]]
    model_calls: list[dict[str, Any]]
    trace: dict[str, Any]
    rollup: LLMOpsRollup


@dataclass(frozen=True, slots=True)
class TraceCorrelationRecord:
    trace_id: str
    run_id: str
    artifact_ids: tuple[str, ...]
    model_call_ids: tuple[str, ...]
    source_pack_id: str | None = None


@dataclass(frozen=True, slots=True)
class OTelExporterConfig:
    endpoint: str
    service_name: str = "crosswordai"
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class OTelExportResult:
    exported: bool
    span_count: int
    endpoint: str
    status_code: int | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AlertRule:
    id: str
    metric: str
    operator: str
    threshold: float
    severity: str
    description: str


class RunInspectionStore(Protocol):
    def get_run(self, run_id: str) -> object | None:
        ...

    def list_artifacts(self, *, run_id: str) -> list[dict[str, Any]]:
        ...

    def list_model_calls(self, *, run_id: str) -> list[dict[str, Any]]:
        ...


class TraceRecorder:
    def __init__(self, *, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or f"trace_{_hash(utc_now_iso())}"
        self.spans: list[Span] = []

    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        started = utc_now_iso()
        start = perf_counter()
        status = "ok"
        events: list[str] = []
        try:
            yield
        except Exception as exc:
            status = "error"
            events.append(type(exc).__name__)
            raise
        finally:
            duration_ms = (perf_counter() - start) * 1000
            self.spans.append(Span(name, started, duration_ms, _stringify(attributes), status, tuple(events)))

    def record_model_call(
        self,
        *,
        task_type: str,
        model_id: str,
        route_id: str,
        latency_ms: float,
        estimated_cost: float,
        cache_hit: bool = False,
        retry_count: int = 0,
    ) -> None:
        self.record_span(
            "model_call",
            duration_ms=latency_ms,
            task_type=task_type,
            model_id=model_id,
            route_id=route_id,
            estimated_cost=estimated_cost,
            cache_hit=cache_hit,
            retry_count=retry_count,
        )

    def record_retrieval_call(
        self,
        *,
        query: str,
        result_count: int,
        latency_ms: float,
        strategy: str = "hybrid",
    ) -> None:
        self.record_span(
            "retrieval_call",
            duration_ms=latency_ms,
            query_hash=_hash(query),
            result_count=result_count,
            strategy=strategy,
        )

    def record_validator(self, *, validator: str, passed: bool, failures: tuple[str, ...] = ()) -> None:
        self.record_span(
            "validator",
            duration_ms=0.0,
            validator=validator,
            passed=passed,
            failure_count=len(failures),
            failures=",".join(failures),
        )

    def record_export(self, *, artifact_type: str, status: str, latency_ms: float = 0.0) -> None:
        self.record_span("export", duration_ms=latency_ms, artifact_type=artifact_type, status=status)

    def record_span(self, name: str, *, duration_ms: float, status: str = "ok", **attributes: object) -> None:
        self.spans.append(Span(name, utc_now_iso(), duration_ms, _stringify(attributes), status))

    def rollup(self, *, publish_decision: PublishDecision | None = None) -> LLMOpsRollup:
        model_spans = [span for span in self.spans if span.name == "model_call"]
        retrieval_spans = [span for span in self.spans if span.name == "retrieval_call"]
        validator_spans = [span for span in self.spans if span.name == "validator"]
        export_spans = [span for span in self.spans if span.name == "export"]
        total_cost = sum(_float_attr(span, "estimated_cost") for span in model_spans)
        retry_count = sum(int(_float_attr(span, "retry_count")) for span in model_spans)
        cache_hit_count = sum(1 for span in model_spans if span.attributes.get("cache_hit") == "true")
        qa_failures = tuple(publish_decision.scorecard.hard_gate_failures) if publish_decision else ()
        return LLMOpsRollup(
            total_cost=round(total_cost, 6),
            total_latency_ms=round(sum(span.duration_ms for span in self.spans), 3),
            retry_count=retry_count,
            cache_hit_rate=round(cache_hit_count / len(model_spans), 3) if model_spans else 0.0,
            model_call_count=len(model_spans),
            retrieval_call_count=len(retrieval_spans),
            validator_count=len(validator_spans),
            export_count=len(export_spans),
            qa_gate_failures=qa_failures,
        )

    def to_dict(self) -> dict[str, object]:
        return {"trace_id": self.trace_id, "spans": [asdict(span) for span in self.spans], "rollup": asdict(self.rollup())}


class OTelTraceExporter:
    def __init__(self, config: OTelExporterConfig, *, http_post: Any | None = None) -> None:
        self.config = config
        self.http_post = http_post or _default_http_post

    def export(self, recorder: TraceRecorder) -> OTelExportResult:
        payload = otlp_payload(recorder, service_name=self.config.service_name)
        try:
            status_code = self.http_post(
                self.config.endpoint,
                json.dumps(payload).encode("utf-8"),
                {"Content-Type": "application/json", **self.config.headers},
                self.config.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - exporter should report transport failures.
            return OTelExportResult(False, len(recorder.spans), self.config.endpoint, failure_reason=str(exc))
        return OTelExportResult(200 <= int(status_code) < 300, len(recorder.spans), self.config.endpoint, int(status_code))


def inspect_run(
    *,
    run_id: str,
    metadata_store: RunInspectionStore,
    trace: TraceRecorder | None = None,
    publish_decision: PublishDecision | None = None,
) -> RunInspectionReport:
    recorder = trace or TraceRecorder()
    run = metadata_store.get_run(run_id)
    run_payload = asdict(run) if run is not None and hasattr(run, "__dataclass_fields__") else run
    model_calls = metadata_store.list_model_calls(run_id=run_id)
    artifacts = metadata_store.list_artifacts(run_id=run_id)
    for call in model_calls:
        recorder.record_model_call(
            task_type=str(call["task_type"]),
            model_id=str(call["model_id"]),
            route_id=str(call["route_id"]),
            latency_ms=float(call["latency_ms"]),
            estimated_cost=float(call["estimated_cost"]),
            cache_hit=bool(call["cache_hit"]),
            retry_count=int(call["retry_count"]),
        )
    return RunInspectionReport(
        run_id=run_id,
        run=run_payload,
        artifacts=artifacts,
        model_calls=model_calls,
        trace=recorder.to_dict(),
        rollup=recorder.rollup(publish_decision=publish_decision),
    )


def correlate_trace(
    *,
    trace: TraceRecorder,
    run_id: str,
    artifacts: list[dict[str, Any]],
    model_calls: list[dict[str, Any]],
    source_pack_id: str | None = None,
) -> TraceCorrelationRecord:
    return TraceCorrelationRecord(
        trace_id=trace.trace_id,
        run_id=run_id,
        artifact_ids=tuple(str(artifact.get("id", artifact.get("artifact_id", ""))) for artifact in artifacts),
        model_call_ids=tuple(str(call.get("id", "")) for call in model_calls),
        source_pack_id=source_pack_id,
    )


def otlp_payload(recorder: TraceRecorder, *, service_name: str = "crosswordai") -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {"key": "crosswordai.trace_id", "value": {"stringValue": recorder.trace_id}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "crosswordai.local"},
                        "spans": [
                            {
                                "name": span.name,
                                "startTimeUnixNano": _iso_to_fake_unix_nano(span.started_at),
                                "endTimeUnixNano": _iso_to_fake_unix_nano(span.started_at) + int(span.duration_ms * 1_000_000),
                                "attributes": [
                                    {"key": key, "value": {"stringValue": value}}
                                    for key, value in span.attributes.items()
                                ],
                                "status": {"code": "STATUS_CODE_ERROR" if span.status == "error" else "STATUS_CODE_OK"},
                            }
                            for span in recorder.spans
                        ],
                    }
                ],
            }
        ]
    }


def dashboard_metrics_payload(recorder: TraceRecorder, *, run_id: str) -> dict[str, Any]:
    rollup = recorder.rollup()
    return {
        "run_id": run_id,
        "trace_id": recorder.trace_id,
        "metrics": asdict(rollup),
        "span_counts": {
            name: sum(1 for span in recorder.spans if span.name == name)
            for name in sorted({span.name for span in recorder.spans})
        },
    }


def default_alert_rules() -> tuple[AlertRule, ...]:
    return (
        AlertRule("qa_gate_failure_rate", "qa_gate_failures", ">", 0.0, "critical", "Any protected QA gate failure should page the operator."),
        AlertRule("model_cost_spike", "total_cost", ">", 10.0, "warning", "Model cost exceeded expected single-run budget."),
        AlertRule("retrieval_zero_results", "retrieval_call_count", "==", 0.0, "warning", "Run produced no retrieval spans."),
        AlertRule("latency_budget", "total_latency_ms", ">", 30000.0, "warning", "Run exceeded latency budget."),
    )


def _stringify(attributes: dict[str, object]) -> dict[str, str]:
    return {key: _string_value(value) for key, value in attributes.items()}


def _string_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _float_attr(span: Span, key: str) -> float:
    try:
        return float(span.attributes.get(key, "0"))
    except ValueError:
        return 0.0


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _default_http_post(endpoint: str, payload: bytes, headers: dict[str, str], timeout: float) -> int:
    request = Request(endpoint, data=payload, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return int(response.status)


def _iso_to_fake_unix_nano(value: str) -> int:
    from datetime import datetime

    return int(datetime.fromisoformat(value).timestamp() * 1_000_000_000)
