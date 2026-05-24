"""Configuration loading for local and future production deployments."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_HOME = Path(".crosswordai")


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path
    artifact_root: Path
    registry_root: Path
    metadata_db: Path
    database_url: str | None
    log_level: str = "INFO"

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Settings":
        data: dict[str, Any] = {}
        if config_path is not None:
            data = json.loads(config_path.read_text(encoding="utf-8"))

        home = Path(
            os.environ.get("CROSSWORDAI_HOME", data.get("home", str(DEFAULT_HOME)))
        )
        artifact_root = Path(data.get("artifact_root", home / "artifacts"))
        registry_root = Path(data.get("registry_root", "config/registries"))
        metadata_db = Path(data.get("metadata_db", home / "crosswordai.db"))
        database_url = data.get("database_url", os.environ.get("CROSSWORDAI_DATABASE_URL"))
        log_level = str(data.get("log_level", os.environ.get("CROSSWORDAI_LOG_LEVEL", "INFO")))
        return cls(
            home=home,
            artifact_root=artifact_root,
            registry_root=registry_root,
            metadata_db=metadata_db,
            database_url=database_url,
            log_level=log_level,
        )

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
