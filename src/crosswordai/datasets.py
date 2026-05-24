"""Distillation dataset creation from lifecycle artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LabeledExample:
    id: str
    task_type: str
    input_ref: str
    output_ref: str
    label: str
    source_decision_ref: str
    lineage_refs: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DatasetCard:
    id: str
    task_type: str
    version: str
    train_count: int
    validation_count: int
    test_count: int
    lineage_refs: tuple[str, ...]
    label_counts: dict[str, int] = field(default_factory=dict)
    export_formats: tuple[str, ...] = ()
    frozen: bool = True


@dataclass(frozen=True, slots=True)
class DistillationDataset:
    id: str
    task_type: str
    version: str
    examples: tuple[LabeledExample, ...]
    train: tuple[LabeledExample, ...]
    validation: tuple[LabeledExample, ...]
    test: tuple[LabeledExample, ...]
    card: DatasetCard


@dataclass(frozen=True, slots=True)
class DatasetBuildReport:
    dataset_id: str
    example_count: int
    accepted_count: int
    rejected_count: int
    repaired_count: int
    quarantined_count: int
    lineage_refs: tuple[str, ...]


def split_examples(examples: list[LabeledExample]) -> tuple[list[LabeledExample], list[LabeledExample], list[LabeledExample]]:
    ordered = sorted(examples, key=lambda example: example.id)
    train_end = max(1, int(len(ordered) * 0.7)) if ordered else 0
    validation_end = max(train_end, int(len(ordered) * 0.85))
    return ordered[:train_end], ordered[train_end:validation_end], ordered[validation_end:]


def examples_from_lifecycle_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    task_type: str,
) -> list[LabeledExample]:
    examples: list[LabeledExample] = []
    for index, artifact in enumerate(artifacts):
        label = _label_for_artifact(artifact)
        input_ref = str(artifact.get("input_ref") or artifact.get("source_pack_id") or artifact.get("puzzle_id") or f"artifact:{index}")
        output_ref = str(artifact.get("output_ref") or artifact.get("artifact_ref") or artifact.get("puzzle_id") or f"output:{index}")
        decision_ref = str(artifact.get("decision_ref") or artifact.get("qa_decision_ref") or artifact.get("status") or label)
        lineage_refs = tuple(
            str(ref)
            for ref in (
                artifact.get("source_pack_id"),
                artifact.get("run_id"),
                artifact.get("model_call_id"),
                artifact.get("qa_decision_ref"),
            )
            if ref
        )
        examples.append(
            LabeledExample(
                id=str(artifact.get("id") or _example_id(task_type, input_ref, output_ref, label, index)),
                task_type=task_type,
                input_ref=input_ref,
                output_ref=output_ref,
                label=label,
                source_decision_ref=decision_ref,
                lineage_refs=lineage_refs,
                metadata={str(key): str(value) for key, value in artifact.get("metadata", {}).items()},
            )
        )
    return examples


def freeze_dataset(
    *,
    dataset_id: str,
    task_type: str,
    version: str,
    examples: list[LabeledExample],
    export_formats: tuple[str, ...] = ("jsonl", "openai_chat_jsonl"),
) -> DistillationDataset:
    train, validation, test = split_examples(examples)
    label_counts = _label_counts(examples)
    lineage_refs = tuple(sorted({ref for example in examples for ref in example.lineage_refs}))
    card = DatasetCard(
        id=dataset_id,
        task_type=task_type,
        version=version,
        train_count=len(train),
        validation_count=len(validation),
        test_count=len(test),
        lineage_refs=lineage_refs,
        label_counts=label_counts,
        export_formats=export_formats,
        frozen=True,
    )
    return DistillationDataset(
        id=dataset_id,
        task_type=task_type,
        version=version,
        examples=tuple(sorted(examples, key=lambda example: example.id)),
        train=tuple(train),
        validation=tuple(validation),
        test=tuple(test),
        card=card,
    )


def build_dataset_from_lifecycle_artifacts(
    *,
    dataset_id: str,
    task_type: str,
    version: str,
    artifacts: list[dict[str, Any]],
) -> tuple[DistillationDataset, DatasetBuildReport]:
    examples = examples_from_lifecycle_artifacts(artifacts, task_type=task_type)
    dataset = freeze_dataset(dataset_id=dataset_id, task_type=task_type, version=version, examples=examples)
    report = DatasetBuildReport(
        dataset_id=dataset.id,
        example_count=len(dataset.examples),
        accepted_count=dataset.card.label_counts.get("accepted", 0),
        rejected_count=dataset.card.label_counts.get("rejected", 0),
        repaired_count=dataset.card.label_counts.get("repaired", 0),
        quarantined_count=dataset.card.label_counts.get("quarantined", 0),
        lineage_refs=dataset.card.lineage_refs,
    )
    return dataset, report


def dataset_card_payload(dataset: DistillationDataset) -> dict[str, Any]:
    return asdict(dataset.card) | {
        "dataset_id": dataset.id,
        "example_count": len(dataset.examples),
        "splits": {
            "train": [example.id for example in dataset.train],
            "validation": [example.id for example in dataset.validation],
            "test": [example.id for example in dataset.test],
        },
    }


def export_jsonl(examples: tuple[LabeledExample, ...] | list[LabeledExample]) -> str:
    return "\n".join(json.dumps(asdict(example), sort_keys=True) for example in examples)


def export_openai_chat_jsonl(examples: tuple[LabeledExample, ...] | list[LabeledExample]) -> str:
    rows = []
    for example in examples:
        rows.append(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": f"Task: {example.task_type}. Produce an output matching the label: {example.label}.",
                    },
                    {"role": "user", "content": example.input_ref},
                    {"role": "assistant", "content": example.output_ref},
                ],
                "metadata": {
                    "example_id": example.id,
                    "label": example.label,
                    "source_decision_ref": example.source_decision_ref,
                    "lineage_refs": list(example.lineage_refs),
                },
            }
        )
    return "\n".join(json.dumps(row, sort_keys=True) for row in rows)


def _label_for_artifact(artifact: dict[str, Any]) -> str:
    explicit = artifact.get("label")
    if explicit:
        return str(explicit)
    status = str(artifact.get("status", "")).lower()
    qa_status = str(artifact.get("qa_status", "")).lower()
    if "repaired" in status or artifact.get("repair_history"):
        return "repaired"
    if "quarantined" in status:
        return "quarantined"
    if status in {"published", "accepted", "succeeded"} or qa_status == "passed":
        return "accepted"
    if status in {"failed", "rejected"} or qa_status.startswith("failed"):
        return "rejected"
    return "accepted"


def _label_counts(examples: list[LabeledExample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for example in examples:
        counts[example.label] = counts.get(example.label, 0) + 1
    return counts


def _example_id(task_type: str, input_ref: str, output_ref: str, label: str, index: int) -> str:
    digest = hashlib.sha256(f"{task_type}:{input_ref}:{output_ref}:{label}:{index}".encode("utf-8")).hexdigest()
    return f"ex_{digest[:16]}"
