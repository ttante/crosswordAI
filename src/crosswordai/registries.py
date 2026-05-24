"""Versioned control-plane registries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    id: str
    version: str
    payload: dict[str, Any]


class JsonRegistry:
    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path
        self.entries = self._load()

    def active_versions(self) -> dict[str, str]:
        return {entry.id: entry.version for entry in self.entries}

    def _load(self) -> list[RegistryEntry]:
        if not self.path.exists():
            raise RegistryError(f"missing registry file: {self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise RegistryError(f"{self.name} registry must be a JSON list")
        entries: list[RegistryEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                raise RegistryError(f"{self.name} registry entries must be objects")
            entry_id = item.get("id")
            version = item.get("version")
            if not entry_id or not version:
                raise RegistryError(f"{self.name} registry entry missing id/version")
            entries.append(RegistryEntry(str(entry_id), str(version), item))
        return entries


def load_registries(root: Path) -> dict[str, JsonRegistry]:
    registries: dict[str, JsonRegistry] = {}
    for name in [
        "models",
        "prompts",
        "routes",
        "policies",
        "source_connectors",
        "wordlists",
        "output_schemas",
    ]:
        registries[name] = JsonRegistry(name, root / f"{name}.json")
    return registries
