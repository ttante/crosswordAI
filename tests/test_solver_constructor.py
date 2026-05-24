from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.solver import AmericanGridValidator, DeterministicGridConstructor, Grid, score_fill


class SolverConstructorTests(unittest.TestCase):
    def test_deterministic_constructor_builds_valid_grid_with_theme_entry(self) -> None:
        wordlist = {
            "ABCDE",
            "FGHIJ",
            "KLMNO",
            "PQRST",
            "UVWXY",
            "AFKPU",
            "BGLQV",
            "CHMRW",
            "DINSX",
            "EJOTY",
        }
        result = DeterministicGridConstructor(wordlist).construct(size=5, theme_entries=["ABCDE"])
        self.assertEqual(result.status, "succeeded")
        assert result.grid is not None
        self.assertTrue(AmericanGridValidator().validate(result.grid).passed)
        self.assertEqual(result.grid.rows[0], "ABCDE")
        assert result.fill_score is not None
        self.assertEqual(result.fill_score.duplicate_count, 0)
        self.assertGreater(result.fill_score.score, 0.9)

    def test_constructor_reports_precise_failure(self) -> None:
        result = DeterministicGridConstructor({"ABCDE"}).construct(size=5, theme_entries=["TOOLONG"])
        self.assertEqual(result.status, "failed")
        self.assertIn("theme_entry_length_mismatch", result.failures)

    def test_fill_scoring_counts_obscure_entries(self) -> None:
        grid = Grid(("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"))
        score = score_fill(grid, {"ABCDE"})
        self.assertGreater(score.obscure_count, 0)

    def test_validator_rejects_duplicate_answers(self) -> None:
        grid = Grid(("ABCDE", "FGHIJ", "KLMNO", "FGHIJ", "EDCBA"))
        result = AmericanGridValidator().validate(grid)
        self.assertFalse(result.passed)
        self.assertIn("duplicate_answers", result.failures)


if __name__ == "__main__":
    unittest.main()
