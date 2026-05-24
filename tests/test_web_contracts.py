from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.web_contracts import error_response, health_response
from crosswordai.web_fixtures import all_contract_fixtures


class WebContractTests(unittest.TestCase):
    def test_health_and_error_contracts_are_json_serializable(self) -> None:
        health_payload = health_response(correlation_id="corr_contract").to_dict()
        error_payload = error_response(
            code="bad_request",
            message="Invalid request.",
            correlation_id="corr_contract",
            details={"field": "theme"},
            remediation="Provide a non-empty theme.",
        ).to_dict()

        self.assertEqual(json.loads(json.dumps(health_payload))["correlation_id"], "corr_contract")
        self.assertEqual(json.loads(json.dumps(error_payload))["error"]["code"], "bad_request")

    def test_frontend_fixtures_cover_initial_contract_shapes(self) -> None:
        fixtures = all_contract_fixtures()

        self.assertEqual(
            set(fixtures),
            {
                "artifact",
                "run_detail",
                "source_pack",
                "player_puzzle",
                "registry_index",
                "batch_summary",
                "report_summary",
            },
        )
        json.dumps(fixtures)
        self.assertEqual(fixtures["player_puzzle"]["export_policy"]["raw_evidence_quotes_included"], False)
        for clue in fixtures["player_puzzle"]["clues"]:
            self.assertNotIn("answer", clue)

    def test_checked_in_json_fixtures_match_contract_keys(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "web" / "contracts.json"
        checked_in = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(set(checked_in), set(all_contract_fixtures()))
        self.assertEqual(checked_in["run_detail"]["run"]["run_id"], "run_web_fixture")
        self.assertEqual(checked_in["player_puzzle"]["grid"]["width"], 5)


if __name__ == "__main__":
    unittest.main()
