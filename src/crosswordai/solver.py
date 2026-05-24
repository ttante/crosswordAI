"""Deterministic crossword grid construction and validation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Grid:
    rows: tuple[str, ...]

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def cell(self, row: int, col: int) -> str:
        return self.rows[row][col]

    def is_block(self, row: int, col: int) -> bool:
        return self.cell(row, col) == "#"


@dataclass(frozen=True, slots=True)
class GridValidationResult:
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FillScore:
    score: float
    duplicate_count: int
    obscure_count: int
    theme_entry_count: int


@dataclass(frozen=True, slots=True)
class GridConstructionResult:
    grid: Grid | None
    status: str
    failures: tuple[str, ...]
    fill_score: FillScore | None = None


class AmericanGridValidator:
    def validate(self, grid: Grid) -> GridValidationResult:
        failures: list[str] = []
        if not grid.rows:
            failures.append("empty_grid")
            return GridValidationResult(False, tuple(failures))
        if any(len(row) != grid.width for row in grid.rows):
            failures.append("ragged_grid")
        if any(char != "#" and not char.isalpha() for row in grid.rows for char in row):
            failures.append("invalid_cell")
        if not _rotationally_symmetric(grid):
            failures.append("not_rotationally_symmetric")
        if not _connected(grid):
            failures.append("open_cells_not_connected")
        if _has_too_short_answer(grid):
            failures.append("answer_too_short")
        if _has_unchecked_letters(grid):
            failures.append("unchecked_letters")
        if _has_duplicate_answers(grid):
            failures.append("duplicate_answers")
        return GridValidationResult(not failures, tuple(failures))


class DeterministicGridConstructor:
    """Conservative deterministic constructor for fully checked open grids."""

    def __init__(self, wordlist: list[str] | set[str]) -> None:
        self.wordlist = {_normalize_word(word) for word in wordlist if _normalize_word(word)}

    @classmethod
    def from_file(cls, path: Path) -> "DeterministicGridConstructor":
        return cls(path.read_text(encoding="utf-8").splitlines())

    def construct(self, *, size: int, theme_entries: list[str] | tuple[str, ...] = ()) -> GridConstructionResult:
        theme_words = tuple(_normalize_word(entry) for entry in theme_entries if _normalize_word(entry))
        failures = self._preflight(size=size, theme_words=theme_words)
        if failures:
            return GridConstructionResult(None, "failed", tuple(failures))

        candidates = sorted(word for word in self.wordlist if len(word) == size)
        prefixes = _prefixes(candidates)
        rows = list(theme_words)
        solution = self._search_rows(size=size, rows=rows, used=set(rows), candidates=candidates, prefixes=prefixes)
        if solution is None:
            return GridConstructionResult(None, "failed", ("no_grid_found",))

        grid = Grid(tuple(solution))
        fill_score = score_fill(grid, self.wordlist, theme_words)
        validation = AmericanGridValidator().validate(grid)
        if not validation.passed:
            return GridConstructionResult(grid, "failed", validation.failures, fill_score)
        return GridConstructionResult(grid, "succeeded", (), fill_score)

    def _preflight(self, *, size: int, theme_words: tuple[str, ...]) -> list[str]:
        failures: list[str] = []
        if size < 3:
            failures.append("size_too_small")
        if any(len(word) != size for word in theme_words):
            failures.append("theme_entry_length_mismatch")
        if any(word not in self.wordlist for word in theme_words):
            failures.append("theme_entry_not_in_wordlist")
        if len(set(theme_words)) != len(theme_words):
            failures.append("duplicate_theme_entries")
        return failures

    def _search_rows(
        self,
        *,
        size: int,
        rows: list[str],
        used: set[str],
        candidates: list[str],
        prefixes: set[str],
    ) -> list[str] | None:
        if len(rows) == size:
            columns = _columns(rows)
            if all(column in self.wordlist for column in columns) and len(set(rows + columns)) == len(rows + columns):
                return rows
            return None

        for word in candidates:
            if word in used:
                continue
            next_rows = rows + [word]
            if not _column_prefixes_valid(next_rows, prefixes):
                continue
            used.add(word)
            solution = self._search_rows(size=size, rows=next_rows, used=used, candidates=candidates, prefixes=prefixes)
            if solution is not None:
                return solution
            used.remove(word)
        return None


def extract_entries(grid: Grid) -> dict[str, list[str]]:
    return {"across": _entries_across(grid), "down": _entries_down(grid)}


def score_fill(grid: Grid, wordlist: set[str], theme_entries: tuple[str, ...] = ()) -> FillScore:
    entries = extract_entries(grid)["across"] + extract_entries(grid)["down"]
    duplicate_count = len(entries) - len(set(entries))
    obscure_count = sum(1 for entry in entries if entry not in wordlist)
    theme_entry_count = sum(1 for entry in entries if entry in set(theme_entries))
    score = max(0.0, 1.0 - duplicate_count * 0.2 - obscure_count * 0.15)
    return FillScore(score, duplicate_count, obscure_count, theme_entry_count)


def _rotationally_symmetric(grid: Grid) -> bool:
    for row in range(grid.height):
        for col in range(grid.width):
            if grid.is_block(row, col) != grid.is_block(grid.height - row - 1, grid.width - col - 1):
                return False
    return True


def _connected(grid: Grid) -> bool:
    open_cells = [(r, c) for r in range(grid.height) for c in range(grid.width) if not grid.is_block(r, c)]
    if not open_cells:
        return False
    seen = {open_cells[0]}
    queue = deque([open_cells[0]])
    while queue:
        row, col = queue.popleft()
        for nr, nc in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= nr < grid.height and 0 <= nc < grid.width and not grid.is_block(nr, nc) and (nr, nc) not in seen:
                seen.add((nr, nc))
                queue.append((nr, nc))
    return len(seen) == len(open_cells)


def _has_too_short_answer(grid: Grid) -> bool:
    return any(len(entry) < 3 for entry in _entries_across(grid) + _entries_down(grid))


def _has_unchecked_letters(grid: Grid) -> bool:
    for row in range(grid.height):
        for col in range(grid.width):
            if grid.is_block(row, col):
                continue
            checked_across = _run_length(grid, row, col, 0, -1) + _run_length(grid, row, col, 0, 1) + 1 >= 3
            checked_down = _run_length(grid, row, col, -1, 0) + _run_length(grid, row, col, 1, 0) + 1 >= 3
            if not checked_across or not checked_down:
                return True
    return False


def _has_duplicate_answers(grid: Grid) -> bool:
    entries = _entries_across(grid) + _entries_down(grid)
    return len(entries) != len(set(entries))


def _run_length(grid: Grid, row: int, col: int, dr: int, dc: int) -> int:
    length = 0
    row += dr
    col += dc
    while 0 <= row < grid.height and 0 <= col < grid.width and not grid.is_block(row, col):
        length += 1
        row += dr
        col += dc
    return length


def _entries_across(grid: Grid) -> list[str]:
    entries: list[str] = []
    for row in grid.rows:
        entries.extend(entry for entry in row.split("#") if entry)
    return entries


def _entries_down(grid: Grid) -> list[str]:
    entries: list[str] = []
    for col in range(grid.width):
        current = ""
        for row in range(grid.height):
            if grid.is_block(row, col):
                if current:
                    entries.append(current)
                    current = ""
            else:
                current += grid.cell(row, col)
        if current:
            entries.append(current)
    return entries


def _normalize_word(word: str) -> str:
    return "".join(char for char in word.upper() if char.isalpha())


def _prefixes(words: list[str]) -> set[str]:
    return {word[:index] for word in words for index in range(1, len(word) + 1)}


def _columns(rows: list[str]) -> list[str]:
    return ["".join(row[index] for row in rows) for index in range(len(rows[0]))]


def _column_prefixes_valid(rows: list[str], prefixes: set[str]) -> bool:
    return all(column in prefixes for column in _columns(rows))
