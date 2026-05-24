from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.core_path import CorePathRequest, HardenedCorePathPipeline
from crosswordai.metadata import LocalMetadataStore
from crosswordai.storage import LocalArtifactStore


class HardenedCorePathTests(unittest.TestCase):
    def test_core_path_persists_artifacts_trace_and_eval_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            notes = tmp_path / "notes.md"
            notes.write_text(
                "Miles Davis recorded Kind of Blue with John Coltrane.\n\n"
                "Kind of Blue is a jazz album with strong source evidence for a classroom crossword.",
                encoding="utf-8",
            )
            artifact_store = LocalArtifactStore(tmp_path / "artifacts")
            metadata_store = LocalMetadataStore(tmp_path / "crosswordai.db")
            result = HardenedCorePathPipeline(
                artifact_store=artifact_store,
                metadata_store=metadata_store,
            ).run(CorePathRequest(theme="Miles Davis", notes_path=notes, puzzle_id="puzzle_core_test"))

            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.eval_result.protected_regressions, 0)
            self.assertIn("source_pack", result.artifact_refs)
            self.assertIn("export_bundle", result.artifact_refs)
            self.assertIn("trace", result.artifact_refs)
            self.assertGreaterEqual(len(metadata_store.list_artifacts(run_id=result.run_id)), 5)
            run = metadata_store.get_run(result.run_id)
            assert run is not None
            self.assertEqual(run.status, "succeeded")
            self.assertTrue(result.trace["spans"])


if __name__ == "__main__":
    unittest.main()
