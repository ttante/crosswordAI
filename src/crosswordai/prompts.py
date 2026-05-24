"""Prompt registry, rendering, structured output validation, and repair."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any


class StructuredOutputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: str
    version: str
    template: str
    task: str = ""
    output_schema_id: str | None = None

    def render(self, **values: str) -> str:
        return Template(self.template).safe_substitute(**values)


@dataclass(frozen=True, slots=True)
class OutputSchema:
    id: str
    version: str
    required_keys: tuple[str, ...]
    property_types: dict[str, str]


class PromptRegistry:
    def __init__(self, prompts: dict[str, PromptTemplate], schemas: dict[str, OutputSchema]) -> None:
        self.prompts = prompts
        self.schemas = schemas

    @classmethod
    def load(cls, *, prompts_path: Path, schemas_path: Path | None = None) -> "PromptRegistry":
        prompts = {}
        raw_prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
        for item in raw_prompts:
            prompt = PromptTemplate(
                id=str(item["id"]),
                version=str(item["version"]),
                task=str(item.get("task", "")),
                template=str(item["template"]),
                output_schema_id=item.get("output_schema_id"),
            )
            prompts[prompt.id] = prompt
        schemas = {}
        if schemas_path is not None and schemas_path.exists():
            raw_schemas = json.loads(schemas_path.read_text(encoding="utf-8"))
            for item in raw_schemas:
                schema = OutputSchema(
                    id=str(item["id"]),
                    version=str(item["version"]),
                    required_keys=tuple(str(key) for key in item.get("required_keys", [])),
                    property_types={str(key): str(value) for key, value in item.get("property_types", {}).items()},
                )
                schemas[schema.id] = schema
        return cls(prompts, schemas)

    def render(self, prompt_id: str, **values: str) -> str:
        return self.prompts[prompt_id].render(**values)

    def schema_for_prompt(self, prompt_id: str) -> OutputSchema | None:
        schema_id = self.prompts[prompt_id].output_schema_id
        return self.schemas.get(schema_id) if schema_id else None


def parse_json_object(text: str, *, required_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        repaired = repair_json_object(text)
        if repaired is None:
            raise StructuredOutputError(str(exc)) from exc
        payload = repaired
    if not isinstance(payload, dict):
        raise StructuredOutputError("model output must be a JSON object")
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise StructuredOutputError(f"model output missing required keys: {', '.join(missing)}")
    return payload


def validate_output_schema(payload: dict[str, Any], schema: OutputSchema) -> None:
    missing = [key for key in schema.required_keys if key not in payload]
    if missing:
        raise StructuredOutputError(f"model output missing required keys: {', '.join(missing)}")
    for key, expected_type in schema.property_types.items():
        if key not in payload:
            continue
        if expected_type == "string" and not isinstance(payload[key], str):
            raise StructuredOutputError(f"{key} must be string")
        if expected_type == "number" and not isinstance(payload[key], (int, float)):
            raise StructuredOutputError(f"{key} must be number")
        if expected_type == "array" and not isinstance(payload[key], list):
            raise StructuredOutputError(f"{key} must be array")
        if expected_type == "object" and not isinstance(payload[key], dict):
            raise StructuredOutputError(f"{key} must be object")


def parse_with_schema(text: str, schema: OutputSchema) -> dict[str, Any]:
    payload = parse_json_object(text, required_keys=schema.required_keys)
    validate_output_schema(payload, schema)
    return payload


def repair_json_object(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    candidate = match.group(0)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
