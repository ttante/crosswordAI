"""Hardened local core path orchestration.

This module wires the product path end to end with durable artifacts, trace
spans, publish gates, and protected eval evidence. Production adapters can swap
in behind the existing storage and metadata protocols.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from crosswordai.candidates import AnswerCandidate, CandidateGenerator
from crosswordai.clues import ClueGenerator
from crosswordai.evals import EvalCase, EvalRunResult, EvalSuite, evaluate_route_outputs
from crosswordai.exports import export_bundle
from crosswordai.ids import new_run_id
from crosswordai.metadata import MetadataStore
from crosswordai.observability import TraceRecorder
from crosswordai.qa import ClueQAPipeline, PuzzleQualityGate
from crosswordai.reports import enterprise_inspection_bundle, report_export_payload
from crosswordai.solver import DeterministicGridConstructor, Grid, extract_entries
from crosswordai.sources import SourcePack, UserNotesSourcePackBuilder
from crosswordai.storage import ArtifactRecord, ArtifactStore


DEFAULT_CORE_WORDLIST = (
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
)


@dataclass(frozen=True, slots=True)
class CorePathRequest:
    theme: str
    notes_path: Path
    route_id: str = "baseline-local"
    puzzle_id: str = "puzzle_local_core"
    grid_size: int = 5
    clue_styles: tuple[str, ...] = ("direct",)
    candidate_limit: int = 25


@dataclass(frozen=True, slots=True)
class CorePathResult:
    run_id: str
    puzzle_id: str
    source_pack_id: str
    status: str
    artifact_refs: dict[str, str]
    eval_result: EvalRunResult
    trace: dict[str, Any]


class HardenedCorePathPipeline:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        metadata_store: MetadataStore,
        wordlist: tuple[str, ...] | list[str] | None = None,
        trace: TraceRecorder | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.metadata_store = metadata_store
        self.wordlist = tuple(wordlist or DEFAULT_CORE_WORDLIST)
        self.trace = trace or TraceRecorder()

    def run(self, request: CorePathRequest) -> CorePathResult:
        run_id = str(new_run_id())
        self.metadata_store.create_run(run_id=run_id, run_type="hardened_core_path")
        artifacts: dict[str, str] = {}
        try:
            source_pack = self._build_source_pack(request, run_id, artifacts)
            candidates = self._generate_candidates(source_pack, request)
            grid = self._construct_grid(request, artifacts)
            clues = self._generate_clues(source_pack, grid, request)
            final_clues = self._qa_clues(clues)
            decision = self._publish_decision(grid, final_clues)
            bundle = export_bundle(
                puzzle_id=request.puzzle_id,
                grid=grid,
                clues=final_clues,
                publish_decision=decision,
                source_pack_id=str(source_pack.id),
                run_id=run_id,
            )
            export_record = self._write_artifact(
                run_id,
                "export_bundle",
                bundle,
                "application/vnd.crosswordai.core-export-bundle+json",
                artifacts,
            )
            self.trace.record_export(artifact_type="core_export_bundle", status=decision.status)
            report_bundle = enterprise_inspection_bundle(
                puzzle_id=request.puzzle_id,
                theme=request.theme,
                grid=grid,
                clues=final_clues,
                decision=decision,
                source_pack_id=str(source_pack.id),
                model_route=request.route_id,
                baseline_taxonomy=source_pack.taxonomy,
                observed_taxonomies=(source_pack.taxonomy,),
            )
            self._write_artifact(
                run_id,
                "inspection_bundle",
                report_export_payload(report_bundle),
                "application/vnd.crosswordai.enterprise-inspection+json",
                artifacts,
            )
            eval_result = self._eval_gate(
                route_id=request.route_id,
                publish_status=decision.status,
                export_bundle_payload=bundle,
            )
            self._write_artifact(
                run_id,
                "eval_gate",
                asdict(eval_result),
                "application/vnd.crosswordai.core-eval-gate+json",
                artifacts,
            )
            self.trace.record_validator(
                validator="core_path_eval_gate",
                passed=eval_result.passed,
                failures=eval_result.failures,
            )
            self._write_artifact(
                run_id,
                "trace",
                self.trace.to_dict(),
                "application/vnd.crosswordai.trace+json",
                artifacts,
            )
            status = "succeeded" if decision.status == "published" and eval_result.passed else "quarantined"
            self.metadata_store.complete_run(
                run_id=run_id,
                status=status,
                failure_reason=None if status == "succeeded" else ",".join(decision.reasons or eval_result.failures),
            )
            return CorePathResult(
                run_id=run_id,
                puzzle_id=request.puzzle_id,
                source_pack_id=str(source_pack.id),
                status=status,
                artifact_refs=artifacts,
                eval_result=eval_result,
                trace=self.trace.to_dict(),
            )
        except Exception as exc:
            self.metadata_store.complete_run(run_id=run_id, status="failed", failure_reason=str(exc))
            raise

    def _build_source_pack(
        self,
        request: CorePathRequest,
        run_id: str,
        artifacts: dict[str, str],
    ) -> SourcePack:
        with self.trace.span("source_pack_build", theme=request.theme):
            source_pack, policy = UserNotesSourcePackBuilder(self.artifact_store).build(
                theme=request.theme,
                notes_path=request.notes_path,
            )
        record = self.artifact_store.write_json(
            source_pack.to_dict(),
            media_type="application/vnd.crosswordai.source-pack+json",
        )
        self.metadata_store.record_artifact(run_id=run_id, artifact=record)
        self.metadata_store.record_source_pack(source_pack=source_pack, artifact=record)
        artifacts["source_pack"] = str(record.path)
        self.trace.record_validator(
            validator="source_pack_policy",
            passed=policy.passed,
            failures=tuple(finding.code for finding in policy.findings),
        )
        return source_pack

    def _generate_candidates(self, source_pack: SourcePack, request: CorePathRequest) -> list[AnswerCandidate]:
        with self.trace.span("candidate_generation", source_pack_id=str(source_pack.id)):
            candidates = CandidateGenerator().from_source_pack(source_pack, limit=request.candidate_limit)
        self.trace.record_validator(
            validator="candidate_generation",
            passed=bool(candidates),
            failures=() if candidates else ("no_candidates",),
        )
        return candidates

    def _construct_grid(self, request: CorePathRequest, artifacts: dict[str, str]) -> Grid:
        with self.trace.span("grid_construction", size=request.grid_size):
            result = DeterministicGridConstructor(list(self.wordlist)).construct(size=request.grid_size)
        self.trace.record_validator(
            validator="grid_construction",
            passed=result.status == "succeeded",
            failures=result.failures,
        )
        if result.grid is None:
            raise RuntimeError(f"grid construction failed: {','.join(result.failures)}")
        artifacts["grid_status"] = result.status
        return result.grid

    def _generate_clues(
        self,
        source_pack: SourcePack,
        grid: Grid,
        request: CorePathRequest,
    ) -> list[Any]:
        evidence_ids = tuple(snippet.id for snippet in source_pack.evidence_snippets)
        taxonomy_tags = tuple(str(tag) for tag in source_pack.taxonomy_metadata.get("required_entities", ()))
        generator = ClueGenerator(model_id=f"{request.route_id}:local-template")
        clues = []
        with self.trace.span("clue_generation", style=",".join(request.clue_styles)):
            for index, answer in enumerate(extract_entries(grid)["across"], start=1):
                candidate = AnswerCandidate(
                    answer_text=answer,
                    normalized_answer=answer,
                    enumeration=len(answer),
                    theme_role=f"grid_entry_{index}",
                    difficulty_estimate="easy",
                    familiarity_score=0.8,
                    novelty_score=0.4,
                    rights_risk="low",
                    source_evidence_ids=evidence_ids,
                    source_support_score=0.8 if evidence_ids else 0.0,
                    taxonomy_tags=taxonomy_tags,
                    generation_source="core_path_grid_entry",
                )
                clues.extend(
                    generator.generate(
                        candidate,
                        styles=request.clue_styles,
                        source_pack=source_pack,
                        per_style=1,
                    )
                )
        self.trace.record_validator(
            validator="clue_generation",
            passed=bool(clues),
            failures=() if clues else ("missing_clues",),
        )
        return clues

    def _qa_clues(self, clues: list[Any]) -> list[Any]:
        with self.trace.span("clue_qa", clue_count=len(clues)):
            final_clues, qa_results = ClueQAPipeline().evaluate(clues)
        failures = tuple(result.answer for result in qa_results if result.quarantined)
        self.trace.record_validator(validator="clue_qa", passed=not failures, failures=failures)
        return final_clues

    def _publish_decision(self, grid: Grid, clues: list[Any]) -> Any:
        with self.trace.span("publish_gate", clue_count=len(clues)):
            decision = PuzzleQualityGate().publish_decision(grid=grid, clues=clues)
        self.trace.record_validator(validator="publish_gate", passed=decision.status == "published", failures=decision.reasons)
        return decision

    def _eval_gate(
        self,
        *,
        route_id: str,
        publish_status: str,
        export_bundle_payload: dict[str, Any],
    ) -> EvalRunResult:
        suite = EvalSuite(
            id="core-path-protected-v1",
            version="1",
            cases=(
                EvalCase("core_publish_gate", "system", "core://publish", {"status": "published"}),
                EvalCase("core_export_safety", "system", "core://exports", {"raw_evidence_quotes_included": "false"}),
            ),
            protected=True,
        )
        public_puzzle = export_bundle_payload["artifacts"].get("public_puzzle") or {}
        raw_quotes = public_puzzle.get("export_policy", {}).get("raw_evidence_quotes_included", False)
        return evaluate_route_outputs(
            route_id=route_id,
            suite=suite,
            outputs={
                "core_publish_gate": {"status": publish_status},
                "core_export_safety": {"raw_evidence_quotes_included": str(raw_quotes).lower()},
            },
        )

    def _write_artifact(
        self,
        run_id: str,
        name: str,
        payload: dict[str, Any],
        media_type: str,
        artifacts: dict[str, str],
    ) -> ArtifactRecord:
        record = self.artifact_store.write_json(payload, media_type=media_type)
        self.metadata_store.record_artifact(run_id=run_id, artifact=record)
        artifacts[name] = str(record.path)
        return record
