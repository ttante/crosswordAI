"""Typed identifiers for durable artifacts and runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class TypedId:
    """Small value object that preserves the ID namespace in string form."""

    value: str
    prefix: ClassVar[str] = "id"

    def __post_init__(self) -> None:
        expected = f"{self.prefix}_"
        if not self.value.startswith(expected):
            raise ValueError(f"{type(self).__name__} must start with {expected!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RunId(TypedId):
    prefix: ClassVar[str] = "run"


@dataclass(frozen=True, slots=True)
class ArtifactId(TypedId):
    prefix: ClassVar[str] = "art"


@dataclass(frozen=True, slots=True)
class SourcePackId(TypedId):
    prefix: ClassVar[str] = "sp"


def new_run_id() -> RunId:
    return RunId(_new_id("run"))


def new_artifact_id() -> ArtifactId:
    return ArtifactId(_new_id("art"))


def new_source_pack_id() -> SourcePackId:
    return SourcePackId(_new_id("sp"))


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}_{uuid4().hex[:12]}"
