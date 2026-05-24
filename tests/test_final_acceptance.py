from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class FinalAcceptanceTests(unittest.TestCase):
    def test_all_plan_tickets_are_tracked_and_complete(self) -> None:
        status = Path("IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (\d+) \| ([^|]+) \| ([^|]+) \|", status, flags=re.MULTILINE)
        tickets = {int(number): state.strip() for number, _title, state in rows}
        self.assertEqual(set(range(1, 30)), set(tickets))
        incomplete = {number: state for number, state in tickets.items() if state != "Complete"}
        self.assertEqual(incomplete, {})

    def test_final_focus_points_to_next_maturity_work(self) -> None:
        status = Path("IMPLEMENTATION_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("P0.6 protected CI eval gate", status)

    def test_maturity_roadmap_has_prioritized_first_production_path(self) -> None:
        roadmap = Path("MATURITY_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("Prioritized Backlog", roadmap)
        self.assertIn("P0.1", roadmap)
        self.assertIn("source pack -> candidates -> grid -> clues -> QA -> exports -> observability -> protected eval gate", roadmap)


if __name__ == "__main__":
    unittest.main()
