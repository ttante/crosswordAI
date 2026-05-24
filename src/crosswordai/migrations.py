"""Database migration runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SqlExecutor(Protocol):
    def execute_script(self, sql: str) -> None:
        ...


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    path: Path
    sql: str


class MigrationRunner:
    def __init__(self, migrations_dir: Path) -> None:
        self.migrations_dir = migrations_dir

    def load(self) -> list[Migration]:
        migrations: list[Migration] = []
        for path in sorted(self.migrations_dir.glob("*.sql")):
            version = path.name.split("_", 1)[0]
            migrations.append(Migration(version=version, path=path, sql=path.read_text(encoding="utf-8")))
        return migrations

    def run(self, executor: SqlExecutor) -> list[str]:
        applied: list[str] = []
        for migration in self.load():
            executor.execute_script(migration.sql)
            applied.append(migration.version)
        return applied
