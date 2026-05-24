"""Command-line interface for the CrosswordAI platform."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from crosswordai.batch import BatchExecutionPolicy, BatchItem, BatchRunSet, LocalBatchExecutor, inspect_batch_run_set
from crosswordai.config import Settings
from crosswordai.connectors import default_connectors
from crosswordai.evals import RouteScore, compare_routes
from crosswordai.experiments import ExperimentMatrix, ExperimentMatrixRunner, experiment_report_payload
from crosswordai.ids import new_run_id, utc_now_iso
from crosswordai.logging import configure_logging
from crosswordai.metadata import metadata_store_from_settings
from crosswordai.registries import load_registries
from crosswordai.retrieval_eval import evaluate_suite, load_retrieval_eval_suite, suite_result_to_dict
from crosswordai.routing import DEFAULT_ADVANCED_ROUTES
from crosswordai.sources import MultiSourcePackBuilder, UserNotesSourcePackBuilder
from crosswordai.storage import LocalArtifactStore
from crosswordai.vectors import SearchResult


LOGGER = logging.getLogger("crosswordai")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = Settings.load(args.config)
    settings.ensure_dirs()
    configure_logging(settings.log_level)
    return args.handler(args, settings)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crosswordai")
    parser.add_argument("--config", type=Path, default=None, help="Optional JSON settings file.")
    subparsers = parser.add_subparsers(required=True)

    noop = subparsers.add_parser("noop", help="Create a no-op run record.")
    noop.set_defaults(handler=_handle_noop)

    registries = subparsers.add_parser("registries", help="Inspect control-plane registries.")
    registries_sub = registries.add_subparsers(required=True)
    inspect = registries_sub.add_parser("inspect", help="Print active registry versions.")
    inspect.set_defaults(handler=_handle_registries_inspect)

    source_pack = subparsers.add_parser("source-pack", help="Build and inspect source packs.")
    source_sub = source_pack.add_subparsers(required=True)
    build = source_sub.add_parser("build", help="Build a source pack from local user notes.")
    build.add_argument("--theme", required=True)
    build.add_argument("--notes", required=True, type=Path)
    build.add_argument(
        "--sources",
        default="",
        help="Comma-separated external source connectors to include, such as wikipedia,wikidata.",
    )
    build.set_defaults(handler=_handle_source_pack_build)
    inspect_source = source_sub.add_parser("inspect", help="Inspect a persisted source-pack summary.")
    inspect_source.add_argument("--id", required=True)
    inspect_source.set_defaults(handler=_handle_source_pack_inspect)

    batch = subparsers.add_parser("batch", help="Batch generation and run-set utilities.")
    batch_sub = batch.add_subparsers(required=True)
    batch_generate = batch_sub.add_parser("generate", help="Create a local batch run set.")
    batch_generate.add_argument("--themes", required=True, type=Path, help="Text file with one theme per line.")
    batch_generate.add_argument("--routes", default="baseline-local", help="Comma-separated route IDs.")
    batch_generate.add_argument("--execute", action="store_true", help="Execute the batch locally after planning.")
    batch_generate.add_argument("--max-cost", type=float, default=None, help="Stop execution once estimated cost is exhausted.")
    batch_generate.add_argument("--cancel-after", type=int, default=None, help="Cancel execution after N completed items.")
    batch_generate.set_defaults(handler=_handle_batch_generate)
    batch_inspect = batch_sub.add_parser("inspect", help="Inspect a persisted batch run-set JSON artifact.")
    batch_inspect.add_argument("--run-set", required=True, type=Path)
    batch_inspect.set_defaults(handler=_handle_batch_inspect)

    experiments = subparsers.add_parser("experiments", help="Experiment and route comparison utilities.")
    experiments_sub = experiments.add_subparsers(required=True)
    compare = experiments_sub.add_parser("compare", help="Compare route scores from a JSON file.")
    compare.add_argument("--scores", required=True, type=Path)
    compare.set_defaults(handler=_handle_experiments_compare)
    routes = experiments_sub.add_parser("routes", help="List advanced route strategies.")
    routes.set_defaults(handler=_handle_experiments_routes)
    matrix = experiments_sub.add_parser("matrix", help="Run a local experiment matrix.")
    matrix.add_argument("--sources", required=True, type=Path, help="Text file with one source-pack ref per line.")
    matrix.add_argument("--models", default="mock-local")
    matrix.add_argument("--prompts", default="clue_candidate")
    matrix.add_argument("--routes", default="baseline-local")
    matrix.add_argument("--retrieval", default="hybrid")
    matrix.add_argument("--judges", default="mock-local")
    matrix.add_argument("--repairs", default="deterministic")
    matrix.add_argument("--taxonomy", default="general_concept")
    matrix.set_defaults(handler=_handle_experiments_matrix)

    retrieval = subparsers.add_parser("retrieval", help="Retrieval evaluation utilities.")
    retrieval_sub = retrieval.add_subparsers(required=True)
    retrieval_eval = retrieval_sub.add_parser("eval", help="Run a retrieval eval suite against fixture results.")
    retrieval_eval.add_argument("--suite", required=True, type=Path)
    retrieval_eval.add_argument("--k", type=int, default=5)
    retrieval_eval.set_defaults(handler=_handle_retrieval_eval)

    return parser


def _handle_noop(args: argparse.Namespace, settings: Settings) -> int:
    run_id = new_run_id()
    artifact_store = LocalArtifactStore(settings.artifact_root)
    metadata_store = metadata_store_from_settings(settings)
    metadata_store.create_run(run_id=str(run_id), run_type="noop")
    payload = {"run_id": str(run_id), "type": "noop", "created_at": utc_now_iso(), "status": "succeeded"}
    record = artifact_store.write_json(payload, media_type="application/vnd.crosswordai.run+json")
    metadata_store.record_artifact(run_id=str(run_id), artifact=record)
    run_record = metadata_store.complete_run(run_id=str(run_id))
    LOGGER.info(
        "noop run completed",
        extra={"run_id": str(run_id), "artifact_id": str(record.artifact_id), "artifact_path": record.path},
    )
    _print_json({"run": asdict(run_record), "artifact": record.to_dict()})
    return 0


def _handle_registries_inspect(args: argparse.Namespace, settings: Settings) -> int:
    registries = load_registries(settings.registry_root)
    _print_json({name: registry.active_versions() for name, registry in registries.items()})
    return 0


def _handle_source_pack_build(args: argparse.Namespace, settings: Settings) -> int:
    artifact_store = LocalArtifactStore(settings.artifact_root)
    metadata_store = metadata_store_from_settings(settings)
    run_id = str(new_run_id())
    metadata_store.create_run(run_id=run_id, run_type="source_pack_build")
    source_names = [source.strip() for source in args.sources.split(",") if source.strip()]
    if source_names:
        builder = MultiSourcePackBuilder(artifact_store, default_connectors())
        source_pack, policy = builder.build(theme=args.theme, notes_path=args.notes, source_names=source_names)
    else:
        builder = UserNotesSourcePackBuilder(artifact_store)
        source_pack, policy = builder.build(theme=args.theme, notes_path=args.notes)
    record = artifact_store.write_json(
        source_pack.to_dict(),
        media_type="application/vnd.crosswordai.source-pack+json",
    )
    metadata_store.record_artifact(run_id=run_id, artifact=record)
    metadata_store.record_source_pack(source_pack=source_pack, artifact=record)
    metadata_store.complete_run(
        run_id=run_id,
        status="succeeded" if policy.passed else "quarantined",
        failure_reason=None if policy.passed else policy.status,
    )
    LOGGER.info(
        "source pack built",
        extra={
            "source_pack_id": str(source_pack.id),
            "artifact_id": str(record.artifact_id),
            "policy_status": policy.status,
        },
    )
    _print_json(
        {
            "run_id": run_id,
            "source_pack_id": str(source_pack.id),
            "policy_status": policy.status,
            "artifact": record.to_dict(),
        }
    )
    return 0 if policy.passed else 2


def _handle_source_pack_inspect(args: argparse.Namespace, settings: Settings) -> int:
    metadata_store = metadata_store_from_settings(settings)
    detail = metadata_store.get_source_pack_detail(args.id)
    if detail is None:
        _print_json({"error": "source_pack_not_found", "source_pack_id": args.id})
        return 1
    _print_json({"source_pack": detail})
    return 0


def _handle_batch_generate(args: argparse.Namespace, settings: Settings) -> int:
    artifact_store = LocalArtifactStore(settings.artifact_root)
    metadata_store = metadata_store_from_settings(settings)
    themes = [line.strip() for line in args.themes.read_text(encoding="utf-8").splitlines() if line.strip()]
    routes = [route.strip() for route in args.routes.split(",") if route.strip()]
    run_id = str(new_run_id())
    metadata_store.create_run(run_id=run_id, run_type="batch_generate")
    run_set = BatchRunSet.create(run_id, themes, routes)
    execution_report = None
    if args.execute:
        execution_report = LocalBatchExecutor(
            artifact_store,
            policy=BatchExecutionPolicy(max_cost=args.max_cost, cancel_after=args.cancel_after),
        ).execute(run_set)
    record = artifact_store.write_json(
        run_set.to_dict() | ({"execution_report": asdict(execution_report)} if execution_report else {}),
        media_type="application/vnd.crosswordai.batch-run-set+json",
    )
    metadata_store.record_artifact(run_id=run_id, artifact=record)
    metadata_store.complete_run(run_id=run_id)
    LOGGER.info(
        "batch run set created",
        extra={"run_set_id": run_set.id, "artifact_id": str(record.artifact_id), "items": len(run_set.items)},
    )
    _print_json(
        {
            "run_set_id": run_set.id,
            "artifact": record.to_dict(),
            "summary": run_set.summary(),
            "execution_report": asdict(execution_report) if execution_report else None,
        }
    )
    return 0


def _handle_batch_inspect(args: argparse.Namespace, settings: Settings) -> int:
    payload = json.loads(args.run_set.read_text(encoding="utf-8"))
    run_set = BatchRunSet(
        id=str(payload["run_set_id"]),
        created_at=str(payload["created_at"]),
        items=[BatchItem(**item) for item in payload.get("items", [])],
    )
    report = inspect_batch_run_set(run_set)
    _print_json({"batch": asdict(report)})
    return 0


def _handle_experiments_compare(args: argparse.Namespace, settings: Settings) -> int:
    raw_scores = json.loads(args.scores.read_text(encoding="utf-8"))
    scores = [
        RouteScore(
            route_id=str(item["route_id"]),
            quality=float(item["quality"]),
            cost=float(item["cost"]),
            latency_ms=float(item["latency_ms"]),
            publish_rate=float(item["publish_rate"]),
        )
        for item in raw_scores
    ]
    _print_json({"leaderboard": [asdict(score) | {"quality_per_dollar": score.quality_per_dollar} for score in compare_routes(scores)]})
    return 0


def _handle_experiments_routes(args: argparse.Namespace, settings: Settings) -> int:
    _print_json({"routes": [asdict(route) for route in DEFAULT_ADVANCED_ROUTES]})
    return 0


def _handle_experiments_matrix(args: argparse.Namespace, settings: Settings) -> int:
    artifact_store = LocalArtifactStore(settings.artifact_root)
    sources = tuple(line.strip() for line in args.sources.read_text(encoding="utf-8").splitlines() if line.strip())
    matrix = ExperimentMatrix.from_axes(
        id=str(new_run_id()),
        models=_split_csv(args.models),
        prompts=_split_csv(args.prompts),
        routes=_split_csv(args.routes),
        retrieval_strategies=_split_csv(args.retrieval),
        judge_models=_split_csv(args.judges),
        repair_strategies=_split_csv(args.repairs),
        source_pack_refs=sources,
        taxonomy=args.taxonomy,
    )
    report = ExperimentMatrixRunner(artifact_store=artifact_store).run(matrix)
    _print_json(experiment_report_payload(matrix=matrix, results=report.results, leaderboard=report.leaderboard) | {"artifact_ref": report.artifact_ref})
    return 0


def _handle_retrieval_eval(args: argparse.Namespace, settings: Settings) -> int:
    suite = load_retrieval_eval_suite(args.suite)
    fixture_results = _fixture_retrieval_results()
    result = evaluate_suite(suite, fixture_results, k=args.k)
    _print_json({"retrieval_eval": suite_result_to_dict(result)})
    return 0 if result.passed else 1


def _fixture_retrieval_results() -> dict[str, list[SearchResult]]:
    return {
        "Miles Davis jazz album": [
            SearchResult(
                id="fixture_music_kind_of_blue",
                text="Kind of Blue is a Miles Davis jazz album.",
                metadata={"source_type": "wikipedia", "taxonomy": "music_artist", "stale": "false"},
                score=0.99,
                vector_score=0.98,
                lexical_score=0.8,
            )
        ],
        "Python decorator function": [
            SearchResult(
                id="fixture_python_decorator",
                text="A Python decorator wraps a function.",
                metadata={"source_type": "documentation", "taxonomy": "technical_topic", "stale": "false"},
                score=0.95,
                vector_score=0.93,
                lexical_score=0.9,
            )
        ],
    }


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


if __name__ == "__main__":
    raise SystemExit(main())
