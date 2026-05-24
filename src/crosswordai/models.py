"""Model adapter, routing, budgeting, retries, and call records."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Protocol
from urllib.request import Request, urlopen

from crosswordai.ids import utc_now_iso


@dataclass(frozen=True, slots=True)
class ModelRequest:
    task_type: str
    prompt: str
    route_id: str = "baseline-local"
    parameters: dict[str, str | int | float | bool] | None = None
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    model_id: str
    text: str
    cache_hit: bool = False
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    retry_count: int = 0


@dataclass(frozen=True, slots=True)
class ModelCallRecord:
    id: str
    run_id: str | None
    task_type: str
    model_id: str
    route_id: str
    prompt_hash: str
    output_hash: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    cache_hit: bool
    retry_count: int
    created_at: str


@dataclass(slots=True)
class BudgetLedger:
    max_cost: float
    spent: float = 0.0

    def reserve(self, amount: float) -> None:
        if self.spent + amount > self.max_cost:
            raise ModelBudgetExceeded(f"model budget exceeded: {self.spent + amount:.4f} > {self.max_cost:.4f}")
        self.spent += amount


class ModelBudgetExceeded(RuntimeError):
    pass


class ModelAdapter(Protocol):
    model_id: str

    def complete(self, request: ModelRequest) -> ModelResponse:
        ...


class ModelCallSink(Protocol):
    def record_model_call(self, record: ModelCallRecord) -> None:
        ...


class MockModelAdapter:
    model_id = "mock-local"

    def complete(self, request: ModelRequest) -> ModelResponse:
        text = f"[{request.task_type}] {request.prompt[:200]}"
        return ModelResponse(
            self.model_id,
            text,
            input_tokens=_estimate_tokens(request.prompt),
            output_tokens=_estimate_tokens(text),
        )


class OllamaModelAdapter:
    def __init__(self, *, model_id: str, base_url: str = "http://localhost:11434") -> None:
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")

    def complete(self, request: ModelRequest) -> ModelResponse:
        payload = json.dumps(
            {
                "model": self.model_id,
                "prompt": request.prompt,
                "stream": False,
                "options": request.parameters or {},
            }
        ).encode("utf-8")
        http_request = Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(http_request, timeout=float((request.parameters or {}).get("timeout", 60))) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = str(body.get("response", ""))
        return ModelResponse(
            self.model_id,
            text,
            input_tokens=_estimate_tokens(request.prompt),
            output_tokens=_estimate_tokens(text),
        )


class OpenAICompatibleAdapter:
    def __init__(self, *, model_id: str, api_key: str, base_url: str) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, request: ModelRequest) -> ModelResponse:
        payload = json.dumps(
            {
                "model": self.model_id,
                "messages": [{"role": "user", "content": request.prompt}],
                **(request.parameters or {}),
            }
        ).encode("utf-8")
        http_request = Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urlopen(http_request, timeout=float((request.parameters or {}).get("timeout", 60))) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = str(body["choices"][0]["message"]["content"])
        usage = body.get("usage", {})
        return ModelResponse(
            self.model_id,
            text,
            input_tokens=int(usage.get("prompt_tokens", _estimate_tokens(request.prompt))),
            output_tokens=int(usage.get("completion_tokens", _estimate_tokens(text))),
        )


class ModelRouter:
    def __init__(
        self,
        adapters: dict[str, ModelAdapter],
        task_routes: dict[str, str],
        *,
        model_costs: dict[str, float] | None = None,
        budget_ledger: BudgetLedger | None = None,
        call_sink: ModelCallSink | None = None,
        max_retries: int = 0,
    ) -> None:
        self.adapters = adapters
        self.task_routes = task_routes
        self.model_costs = model_costs or {}
        self.budget_ledger = budget_ledger
        self.call_sink = call_sink
        self.max_retries = max_retries
        self.cache: dict[str, ModelResponse] = {}

    def complete(self, request: ModelRequest) -> ModelResponse:
        model_id = self.task_routes.get(request.task_type)
        if model_id is None:
            raise ValueError(f"no model route configured for task: {request.task_type}")
        if model_id not in self.adapters:
            raise ValueError(f"no model adapter configured for model: {model_id}")

        cache_key = _cache_key(request, model_id)
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            response = ModelResponse(
                cached.model_id,
                cached.text,
                cache_hit=True,
                latency_ms=0.0,
                input_tokens=cached.input_tokens,
                output_tokens=cached.output_tokens,
                estimated_cost=0.0,
                retry_count=0,
            )
            self._record(request, response)
            return response

        retry_count = 0
        last_error: Exception | None = None
        while retry_count <= self.max_retries:
            started = time.perf_counter()
            try:
                response = self.adapters[model_id].complete(request)
                latency_ms = (time.perf_counter() - started) * 1000
                estimated_cost = self._estimate_cost(model_id, response)
                if self.budget_ledger is not None:
                    self.budget_ledger.reserve(estimated_cost)
                response = ModelResponse(
                    response.model_id,
                    response.text,
                    cache_hit=False,
                    latency_ms=latency_ms,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    estimated_cost=estimated_cost,
                    retry_count=retry_count,
                )
                self.cache[cache_key] = response
                self._record(request, response)
                return response
            except Exception as exc:
                last_error = exc
                retry_count += 1
        assert last_error is not None
        raise last_error

    def _estimate_cost(self, model_id: str, response: ModelResponse) -> float:
        cost_per_token = self.model_costs.get(model_id, 0.0)
        return (response.input_tokens + response.output_tokens) * cost_per_token

    def _record(self, request: ModelRequest, response: ModelResponse) -> None:
        if self.call_sink is None:
            return
        record = ModelCallRecord(
            id=f"mc_{_hash_text(request.task_type + response.model_id + utc_now_iso())[:16]}",
            run_id=request.run_id,
            task_type=request.task_type,
            model_id=response.model_id,
            route_id=request.route_id,
            prompt_hash=_hash_text(request.prompt),
            output_hash=_hash_text(response.text),
            latency_ms=response.latency_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost=response.estimated_cost,
            cache_hit=response.cache_hit,
            retry_count=response.retry_count,
            created_at=utc_now_iso(),
        )
        self.call_sink.record_model_call(record)


def _cache_key(request: ModelRequest, model_id: str) -> str:
    payload = {
        "model_id": model_id,
        "task_type": request.task_type,
        "prompt": request.prompt,
        "route_id": request.route_id,
        "parameters": request.parameters or {},
    }
    return _hash_text(json.dumps(payload, sort_keys=True))


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))
