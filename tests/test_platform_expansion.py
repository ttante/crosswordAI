from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crosswordai.candidates import CandidateGenerator
from crosswordai.connectors import (
    MusicBrainzConnector,
    OpenLibraryConnector,
    WikipediaConnector,
    WikidataConnector,
)
from crosswordai.graph import Entity, KnowledgeGraph, Relationship
from crosswordai.metadata import LocalMetadataStore
from crosswordai.models import BudgetLedger, MockModelAdapter, ModelBudgetExceeded, ModelRequest, ModelRouter
from crosswordai.prompts import (
    PromptRegistry,
    PromptTemplate,
    StructuredOutputError,
    parse_json_object,
    parse_with_schema,
    repair_json_object,
)
from crosswordai.retrieval_eval import (
    RetrievalEvalCase,
    cluster_failures,
    evaluate_results,
    evaluate_suite,
    load_retrieval_eval_suite,
)
from crosswordai.sources import MultiSourcePackBuilder, UserNotesSourcePackBuilder
from crosswordai.storage import LocalArtifactStore
from crosswordai.taxonomy import RuleBasedTaxonomyClassifier, load_taxonomy_definitions
from crosswordai.vectors import InMemoryHybridIndex, SearchResult


class PlatformExpansionTests(unittest.TestCase):
    def test_external_connectors_parse_live_api_shapes_with_fake_fetcher(self) -> None:
        class Fetcher:
            def fetch_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, object]:
                if "wikipedia" in url:
                    return {
                        "query": {
                            "pages": {
                                "1": {
                                    "title": "Miles Davis",
                                    "extract": "Miles Davis was an American jazz trumpeter.",
                                    "fullurl": "https://en.wikipedia.org/wiki/Miles_Davis",
                                }
                            }
                        }
                    }
                if "wikidata" in url:
                    return {"search": [{"id": "Q93341", "label": "Miles Davis", "description": "American jazz musician"}]}
                if "musicbrainz" in url:
                    return {
                        "artists": [
                            {
                                "id": "abc",
                                "name": "Miles Davis",
                                "disambiguation": "jazz trumpeter",
                                "tags": [{"name": "jazz"}],
                            }
                        ]
                    }
                return {"docs": [{"title": "Kind of Blue", "author_name": ["Ashley Kahn"], "key": "/works/OL1W"}]}

        self.assertIn("jazz trumpeter", WikipediaConnector(Fetcher()).fetch("Miles Davis").content)
        self.assertIn("Q93341", WikidataConnector(Fetcher()).fetch("Miles Davis").content)
        self.assertIn("Tags: jazz", MusicBrainzConnector(Fetcher()).fetch("Miles Davis").content)
        self.assertIn("Ashley Kahn", OpenLibraryConnector(Fetcher()).fetch("Kind of Blue").content)

    def test_multi_source_builder_combines_notes_and_two_external_sources(self) -> None:
        class StaticConnector:
            def __init__(self, source_type: str, content: str, trust: float) -> None:
                self.source_type = source_type
                self.content = content
                self.trust = trust

            def fetch(self, theme: str):
                from crosswordai.connectors import ConnectorResult

                return ConnectorResult(
                    source_type=self.source_type,
                    title=f"{theme} {self.source_type}",
                    url_or_path=f"https://example.test/{self.source_type}/{theme}",
                    provider=self.source_type,
                    trust_score=self.trust,
                    license_or_rights_status="metadata_only",
                    content=self.content,
                    raw_metadata={"source": self.source_type},
                )

        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text("Miles Davis jazz album classroom notes.", encoding="utf-8")
            store = LocalArtifactStore(Path(tmp) / "artifacts")
            builder = MultiSourcePackBuilder(
                store,
                {
                    "wikipedia": StaticConnector("wikipedia", "Miles Davis jazz trumpeter biography.", 0.75),
                    "wikidata": StaticConnector("wikidata", "Miles Davis entity Q93341 metadata.", 0.85),
                },
            )
            source_pack, policy = builder.build(
                theme="Miles Davis",
                notes_path=notes,
                source_names=["wikipedia", "wikidata"],
            )
            self.assertTrue(policy.passed)
            self.assertEqual(len(source_pack.source_documents), 3)
            self.assertEqual({doc.source_type for doc in source_pack.source_documents}, {"user_notes", "wikipedia", "wikidata"})
            self.assertEqual(source_pack.taxonomy, "music_artist")
            self.assertGreaterEqual(len(source_pack.evidence_snippets), 3)

    def test_knowledge_graph_relationships_create_clue_angles(self) -> None:
        graph = KnowledgeGraph()
        graph.add_entity(Entity("miles", "sp1", "Miles Davis", "person"))
        graph.add_entity(Entity("kind", "sp1", "Kind of Blue", "album"))
        graph.add_relationship(Relationship("rel1", "sp1", "miles", "released", "kind", ("ev1",), 0.9))
        self.assertEqual(graph.related("miles")[0].name, "Kind of Blue")
        self.assertIn("released", graph.clue_angles("miles")[0]["angle"])
        self.assertEqual(graph.clue_angles("miles")[0]["source_evidence_ids"], ["ev1"])

    def test_knowledge_graph_persists_with_source_pack_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            notes = tmp_path / "notes.md"
            notes.write_text("Miles Davis recorded Kind of Blue with John Coltrane.", encoding="utf-8")
            artifact_store = LocalArtifactStore(tmp_path / "artifacts")
            metadata_store = LocalMetadataStore(tmp_path / "crosswordai.db")
            source_pack, _ = UserNotesSourcePackBuilder(artifact_store).build(theme="Miles Davis", notes_path=notes)
            metadata_store.create_run(run_id="run_graph", run_type="source_pack_build")
            artifact = artifact_store.write_json(source_pack.to_dict())
            metadata_store.record_artifact(run_id="run_graph", artifact=artifact)
            metadata_store.record_source_pack(source_pack=source_pack, artifact=artifact)
            detail = metadata_store.get_source_pack_detail(str(source_pack.id))
            assert detail is not None
            self.assertIn("taxonomy_metadata", detail)
            evidence_id = source_pack.evidence_snippets[0].id

            graph = KnowledgeGraph()
            graph.add_entity(
                Entity(
                    "miles",
                    str(source_pack.id),
                    "Miles Davis",
                    "person",
                    ("Miles",),
                    (evidence_id,),
                    0.95,
                )
            )
            graph.add_entity(
                Entity(
                    "kind",
                    str(source_pack.id),
                    "Kind of Blue",
                    "album",
                    (),
                    (evidence_id,),
                    0.9,
                )
            )
            graph.add_relationship(
                Relationship(
                    "rel_miles_kind",
                    str(source_pack.id),
                    "miles",
                    "recorded",
                    "kind",
                    (evidence_id,),
                    0.9,
                )
            )

            metadata_store.record_graph(graph=graph)
            loaded = metadata_store.load_graph(str(source_pack.id))
            self.assertEqual(loaded.entities["miles"].aliases, ("Miles",))
            self.assertEqual(loaded.related("miles", predicate="recorded")[0].name, "Kind of Blue")
            angle = loaded.clue_angles("miles")[0]
            self.assertEqual(angle["source_evidence_ids"], [evidence_id])
            self.assertGreaterEqual(angle["confidence"], 0.9)

    def test_taxonomy_classifier_detects_music(self) -> None:
        result = RuleBasedTaxonomyClassifier().classify("Miles Davis", "jazz album trumpet")
        self.assertEqual(result.taxonomy, "music_artist")
        self.assertIn("musicbrainz", result.preferred_sources)
        self.assertEqual(result.rights_threshold, "strict")
        self.assertEqual(result.retrieval_policy["min_source_trust"], 0.7)

    def test_taxonomy_definitions_load_from_config(self) -> None:
        definitions = load_taxonomy_definitions(Path("config/taxonomies.json"))
        ids = {definition.id for definition in definitions}
        self.assertIn("music_artist", ids)
        self.assertIn("general_concept", ids)

    def test_source_pack_uses_taxonomy_classifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text("Jazz trumpet album notes about songs and collaborators.", encoding="utf-8")
            store = LocalArtifactStore(Path(tmp) / "artifacts")
            source_pack, _ = UserNotesSourcePackBuilder(store).build(theme="Miles Davis", notes_path=notes)
            self.assertEqual(source_pack.taxonomy, "music_artist")
            self.assertGreater(source_pack.taxonomy_confidence, 0.5)
            self.assertEqual(source_pack.taxonomy_metadata["rights_threshold"], "strict")

    def test_retrieval_eval_metrics(self) -> None:
        index = InMemoryHybridIndex()
        index.add(id="relevant", text="Miles Davis jazz album", metadata={"source_type": "wikipedia", "stale": "false"})
        index.add(id="other", text="Python class decorator", metadata={"source_type": "documentation", "stale": "false"})
        results = index.search("jazz album")
        metrics = evaluate_results(
            results,
            RetrievalEvalCase(
                "jazz album",
                ("relevant",),
                required_source_types=("wikipedia",),
                min_recall_at_k=1.0,
                min_evidence_precision=1.0,
            ),
            k=1,
        )
        self.assertEqual(metrics.recall_at_k, 1.0)
        self.assertEqual(metrics.evidence_precision, 1.0)
        self.assertEqual(metrics.source_diversity, 1)
        self.assertTrue(metrics.passed)

    def test_retrieval_eval_suite_and_failure_clustering(self) -> None:
        suite = load_retrieval_eval_suite(Path("evals/retrieval/golden-v1.json"))
        self.assertEqual(suite.id, "retrieval-golden-v1")
        passing = evaluate_suite(
            suite,
            {
                "Miles Davis jazz album": [
                    SearchResult(
                        "fixture_music_kind_of_blue",
                        "Kind of Blue",
                        {"source_type": "wikipedia", "stale": "false"},
                        1.0,
                    )
                ],
                "Python decorator function": [
                    SearchResult(
                        "fixture_python_decorator",
                        "decorator",
                        {"source_type": "documentation", "stale": "false"},
                        1.0,
                    )
                ],
            },
            k=1,
        )
        self.assertTrue(passing.passed)
        failing = evaluate_suite(suite, {}, k=1)
        self.assertFalse(failing.passed)
        self.assertEqual(failing.failure_clusters["no_results"], 2)
        self.assertIn("low_recall", cluster_failures(failing.case_results))

    def test_model_router_caches_responses(self) -> None:
        router = ModelRouter({"mock-local": MockModelAdapter()}, {"qa": "mock-local"})
        request = ModelRequest(task_type="qa", prompt="Check this clue")
        first = router.complete(request)
        second = router.complete(request)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)

    def test_model_router_tracks_budget_and_persists_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = LocalMetadataStore(Path(tmp) / "crosswordai.db")
            metadata.create_run(run_id="run_model", run_type="model_test")
            router = ModelRouter(
                {"mock-local": MockModelAdapter()},
                {"qa": "mock-local"},
                model_costs={"mock-local": 0.001},
                budget_ledger=BudgetLedger(max_cost=1.0),
                call_sink=metadata,
            )
            response = router.complete(ModelRequest(task_type="qa", prompt="Check this clue", run_id="run_model"))
            self.assertGreater(response.estimated_cost, 0)
            calls = metadata.list_model_calls(run_id="run_model")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["model_id"], "mock-local")

    def test_model_router_enforces_budget(self) -> None:
        router = ModelRouter(
            {"mock-local": MockModelAdapter()},
            {"qa": "mock-local"},
            model_costs={"mock-local": 10.0},
            budget_ledger=BudgetLedger(max_cost=0.01),
        )
        with self.assertRaises(ModelBudgetExceeded):
            router.complete(ModelRequest(task_type="qa", prompt="this is too expensive"))

    def test_prompt_template_and_json_parser(self) -> None:
        prompt = PromptTemplate("p", "1", "Theme: $theme").render(theme="Jazz")
        self.assertEqual(prompt, "Theme: Jazz")
        self.assertEqual(parse_json_object('{"answer": "MILES"}', required_keys=("answer",))["answer"], "MILES")
        with self.assertRaises(StructuredOutputError):
            parse_json_object("[]")

    def test_prompt_registry_schema_validation_and_repair(self) -> None:
        registry = PromptRegistry.load(
            prompts_path=Path("config/registries/prompts.json"),
            schemas_path=Path("config/registries/output_schemas.json"),
        )
        rendered = registry.render("clue_candidate", style="direct", answer="MILES", evidence="jazz trumpeter")
        self.assertIn("MILES", rendered)
        schema = registry.schema_for_prompt("clue_candidate")
        assert schema is not None
        payload = parse_with_schema('prefix {"answer": "MILES", "clue": "Jazz trumpeter Davis", "confidence": 0.9}', schema)
        self.assertEqual(payload["answer"], "MILES")
        self.assertEqual(repair_json_object('bad {"ok": true} tail'), {"ok": True})
        with self.assertRaises(StructuredOutputError):
            parse_with_schema('{"answer": "MILES", "clue": 3, "confidence": 0.9}', schema)

    def test_candidate_generation_from_source_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text("Miles Davis recorded Kind of Blue with John Coltrane.", encoding="utf-8")
            store = LocalArtifactStore(Path(tmp) / "artifacts")
            source_pack, _ = UserNotesSourcePackBuilder(store).build(theme="Miles Davis", notes_path=notes)
            candidates = CandidateGenerator().from_source_pack(source_pack)
            normalized = {candidate.normalized_answer for candidate in candidates}
            self.assertIn("MILESDAVIS", normalized)
            self.assertIn("KINDOFBLUE", normalized)

    def test_candidate_generation_uses_graph_retrieval_taxonomy_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text(
                "Miles Davis recorded Kind of Blue.\n\nKind of Blue is a jazz album.",
                encoding="utf-8",
            )
            store = LocalArtifactStore(Path(tmp) / "artifacts")
            source_pack, _ = UserNotesSourcePackBuilder(store).build(theme="Miles Davis", notes_path=notes)
            evidence_id = source_pack.evidence_snippets[0].id
            graph = KnowledgeGraph()
            graph.add_entity(
                Entity(
                    "kind",
                    str(source_pack.id),
                    "Kind of Blue",
                    "album",
                    ("KOB",),
                    (evidence_id,),
                    0.95,
                )
            )
            graph.add_entity(
                Entity(
                    "miles",
                    str(source_pack.id),
                    "Miles Davis",
                    "person",
                    (),
                    (evidence_id,),
                    0.9,
                )
            )
            graph.add_relationship(
                Relationship(
                    "rel1",
                    str(source_pack.id),
                    "miles",
                    "recorded",
                    "kind",
                    (evidence_id,),
                    0.95,
                )
            )
            retrieval_results = [
                SearchResult(
                    "retrieval_kind",
                    "Kind of Blue jazz album",
                    {
                        "evidence_snippet_id": "ev_retrieved",
                        "taxonomy": "music_artist",
                        "rights_risk": "low",
                    },
                    0.9,
                )
            ]
            candidates = CandidateGenerator(min_source_support=0.2).from_source_pack(
                source_pack,
                graph=graph,
                retrieval_results=retrieval_results,
            )
            by_answer = {candidate.normalized_answer: candidate for candidate in candidates}
            self.assertIn("KINDOFBLUE", by_answer)
            self.assertIn(by_answer["KINDOFBLUE"].generation_source, {"knowledge_graph", "knowledge_graph_relationship"})
            self.assertGreaterEqual(by_answer["KINDOFBLUE"].source_support_score, 0.5)
            self.assertTrue(set(by_answer["KINDOFBLUE"].source_evidence_ids) >= {evidence_id})
            self.assertTrue(any(candidate.theme_role.startswith("graph_") or candidate.theme_role.startswith("relationship_") for candidate in candidates))

    def test_candidate_generation_filters_low_source_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.md"
            notes.write_text("Miles Davis recorded Kind of Blue.", encoding="utf-8")
            store = LocalArtifactStore(Path(tmp) / "artifacts")
            source_pack, _ = UserNotesSourcePackBuilder(store).build(theme="Miles Davis", notes_path=notes)
            candidates = CandidateGenerator(min_source_support=0.99).from_source_pack(source_pack)
            self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
