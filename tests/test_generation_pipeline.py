from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.agents import AgentBudget, ClueCriticWorkflow
from crosswordai.candidates import AnswerCandidate
from crosswordai.clues import ClueCandidate, ClueGenerator, ClueQualityGate
from crosswordai.exports import puzzle_json
from crosswordai.qa import ClueQAPipeline, PuzzleQualityGate
from crosswordai.solver import AmericanGridValidator, Grid, extract_entries
from crosswordai.sources import EvidenceSnippet


class GenerationPipelineTests(unittest.TestCase):
    def test_grid_validator_accepts_simple_checked_grid(self) -> None:
        grid = Grid(("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"))
        result = AmericanGridValidator().validate(grid)
        self.assertTrue(result.passed)
        self.assertEqual(extract_entries(grid)["across"][0], "ABCDE")

    def test_grid_validator_rejects_asymmetry(self) -> None:
        grid = Grid(("ABCD#", "FGHIJ", "KLMNO", "PQRST", "UVWXY"))
        result = AmericanGridValidator().validate(grid)
        self.assertFalse(result.passed)
        self.assertIn("not_rotationally_symmetric", result.failures)

    def test_clue_generation_and_qa(self) -> None:
        candidate = AnswerCandidate(
            answer_text="MILES",
            normalized_answer="MILES",
            enumeration=5,
            theme_role="source_backed",
            difficulty_estimate="easy",
            familiarity_score=0.9,
            novelty_score=0.5,
            rights_risk="low",
            source_evidence_ids=("ev1",),
        )
        clue = ClueGenerator().generate(candidate)[0]
        checked = ClueQualityGate().validate(clue)
        self.assertEqual(checked.qa_status, "passed")

    def test_evidence_grounded_multi_style_clues_include_lineage(self) -> None:
        candidate = AnswerCandidate(
            answer_text="KINDOFBLUE",
            normalized_answer="KINDOFBLUE",
            enumeration=10,
            theme_role="music_theme_entry",
            difficulty_estimate="standard",
            familiarity_score=0.95,
            novelty_score=0.4,
            rights_risk="low",
            source_evidence_ids=("ev_music",),
            source_support_score=0.9,
        )
        snippet = EvidenceSnippet(
            id="ev_music",
            source_document_id="doc_music",
            snippet_text="Kind of Blue is a fan-favorite Miles Davis album with enduring jazz influence.",
            start_locator=0,
            end_locator=83,
            snippet_hash="hash",
            rights_risk="low",
            allowed_use="internal_evidence",
        )
        clues = ClueGenerator().generate(
            candidate,
            styles=("trivia", "expert", "classroom"),
            evidence_snippets=(snippet,),
            per_style=1,
        )
        self.assertEqual(len(clues), 3)
        self.assertTrue(all(clue.source_evidence_ids == ("ev_music",) for clue in clues))
        self.assertTrue(all(clue.evidence_quotes for clue in clues))
        self.assertTrue(all(clue.model_lineage for clue in clues))
        self.assertEqual({clue.clue_style for clue in clues}, {"trivia", "expert", "classroom"})

    def test_clue_qa_pipeline_repairs_or_quarantines(self) -> None:
        repairable = ClueCandidate("MILES", "MILES is the answer", "trivia", "easy", ("ev1",), 0.9, 0.2, "low")
        unsafe = ClueCandidate("MILES", "Too risky", "trivia", "easy", ("ev1",), 0.1, 0.9, "high")
        final_clues, results = ClueQAPipeline().evaluate([repairable, unsafe])
        self.assertEqual(final_clues[0].qa_status, "passed")
        self.assertTrue(final_clues[0].repair_history)
        self.assertTrue(results[1].quarantined)
        self.assertIn("high_rights_risk", results[1].failures)

    def test_agentic_critic_repairs_when_possible(self) -> None:
        clue = ClueCandidate("MILES", "Too vague", "trivia", "easy", ("ev1",), 0.9, 0.2, "low")
        final, decisions = ClueCriticWorkflow().run(clue)
        self.assertEqual(final.qa_status, "passed")
        self.assertTrue(decisions)

    def test_agentic_critic_report_records_roles_and_budget(self) -> None:
        clue = ClueCandidate("MILES", "Too vague", "trivia", "easy", ("ev1",), 0.9, 0.2, "low")
        report = ClueCriticWorkflow(budget=AgentBudget(max_iterations=2, max_cost=0.05)).run_report(clue)
        self.assertEqual(report.final_clue.qa_status, "passed")
        self.assertTrue(report.role_specs)
        self.assertTrue(any(decision.tool_calls for decision in report.decisions))
        self.assertFalse(any(role.can_override_hard_gates for role in report.role_specs))

    def test_publish_and_export(self) -> None:
        grid = Grid(("ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"))
        clue = ClueCandidate("ABCDE", "Evidence-backed clue", "direct", "easy", ("ev1",), 0.1, 0.9, "low", "passed")
        decision = PuzzleQualityGate().publish_decision(grid=grid, clues=[clue])
        payload = puzzle_json(
            puzzle_id="puzzle_1",
            grid=grid,
            clues=[clue],
            publish_decision=decision,
            source_pack_id="sp_1",
        )
        self.assertEqual(decision.status, "published")
        self.assertEqual(payload["publish_decision"]["status"], "published")


if __name__ == "__main__":
    unittest.main()
