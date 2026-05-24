from __future__ import annotations

import sys
import tempfile
import unittest
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - depends on optional web dependency install.
    httpx = None  # type: ignore[assignment]

from crosswordai.config import Settings


@unittest.skipIf(httpx is None, "FastAPI test dependencies are not installed")
class WebApiTests(unittest.TestCase):
    def _app(self):
        from crosswordai.web_api import create_app

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_path = Path(tmp.name)
        settings = Settings(
            home=tmp_path / "home",
            artifact_root=tmp_path / "artifacts",
            registry_root=Path("config/registries"),
            metadata_db=tmp_path / "home" / "crosswordai.db",
            database_url=None,
        )
        return create_app(settings=settings)

    def test_health_returns_versioned_contract_and_correlation_id(self) -> None:
        async def run() -> None:
            transport = httpx.ASGITransport(app=self._app())
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health", headers={"x-correlation-id": "corr_test"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["x-correlation-id"], "corr_test")
            payload = response.json()
            self.assertEqual(payload["service"], "crosswordai-web")
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["correlation_id"], "corr_test")
            self.assertIn("version", payload)
            self.assertIn("dependencies", payload)

        asyncio.run(run())

    def test_missing_route_uses_structured_error_shape(self) -> None:
        async def run() -> None:
            transport = httpx.ASGITransport(app=self._app())
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/missing", headers={"x-correlation-id": "corr_missing"})

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.headers["x-correlation-id"], "corr_missing")
            payload = response.json()
            self.assertEqual(payload["correlation_id"], "corr_missing")
            self.assertEqual(payload["error"]["code"], "not_found")
            self.assertIn("message", payload["error"])
            self.assertIn("details", payload["error"])
            self.assertIn("remediation", payload["error"])

        asyncio.run(run())

    def test_source_pack_endpoints_build_and_read_player_safe_metadata(self) -> None:
        async def run() -> None:
            transport = httpx.ASGITransport(app=self._app())
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/source-packs",
                    json={
                        "theme": "Miles Davis",
                        "notes": "Miles Davis recorded Kind of Blue with John Coltrane.",
                    },
                )
                self.assertEqual(response.status_code, 201)
                payload = response.json()
                source_pack_id = payload["source_pack"]["source_pack_id"]
                self.assertTrue(source_pack_id.startswith("sp_"))
                self.assertEqual(payload["run"]["status"], "succeeded")
                self.assertEqual(payload["source_pack"]["theme"], "Miles Davis")
                self.assertTrue(payload["source_pack"]["evidence_previews"])

                detail = await client.get(f"/api/source-packs/{source_pack_id}")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["source_pack_id"], source_pack_id)

        asyncio.run(run())

    def test_generation_endpoints_create_run_artifact_and_player_safe_puzzle(self) -> None:
        async def run() -> None:
            app = self._app()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/puzzles/generate",
                    json={
                        "theme": "Miles Davis",
                        "notes": "Miles Davis recorded Kind of Blue with John Coltrane.\n"
                        "Kind of Blue is a jazz album with strong source evidence.",
                        "puzzle_id": "puzzle_web_api_test",
                    },
                )
                self.assertEqual(response.status_code, 201)
                generated = response.json()
                run_id = generated["run"]["run_id"]
                self.assertEqual(generated["run"]["status"], "succeeded")
                self.assertEqual(generated["run"]["puzzle_id"], "puzzle_web_api_test")
                self.assertTrue(generated["artifacts"])

                runs = await client.get("/api/runs")
                self.assertEqual(runs.status_code, 200)
                self.assertIn(run_id, {item["run_id"] for item in runs.json()["runs"]})

                run_detail = await client.get(f"/api/runs/{run_id}")
                self.assertEqual(run_detail.status_code, 200)
                self.assertEqual(run_detail.json()["run"]["run_id"], run_id)

                first_artifact_id = run_detail.json()["artifacts"][0]["artifact_id"]
                artifact = await client.get(f"/api/artifacts/{first_artifact_id}")
                self.assertEqual(artifact.status_code, 200)

                puzzle = await client.get("/api/puzzles/puzzle_web_api_test")
                self.assertEqual(puzzle.status_code, 200)
                puzzle_payload = puzzle.json()
                self.assertEqual(puzzle_payload["puzzle_id"], "puzzle_web_api_test")
                self.assertEqual(puzzle_payload["export_policy"]["answer_key_included"], False)
                self.assertNotIn("answer", puzzle_payload["clues"][0])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
