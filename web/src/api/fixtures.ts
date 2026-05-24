import type {
  ArtifactSummary,
  BatchSummaryResponse,
  HealthResponse,
  PlayerPuzzleResponse,
  RegistryIndexResponse,
  ReportSummaryResponse,
  RunDetailResponse,
  RunListResponse,
  SourcePackBuildResponse,
  SourcePackResponse
} from "./types";

const fixtureTime = "2026-05-24T00:00:00+00:00";

export const healthFixture: HealthResponse = {
  service: "crosswordai-web",
  version: "0.1.0",
  status: "ok",
  correlation_id: "corr_web_fixture",
  dependencies: {
    artifact_root: ".crosswordai/artifacts",
    metadata_db: ".crosswordai/crosswordai.db",
    registry_root: "config/registries"
  }
};

export const artifactFixture: ArtifactSummary = {
  artifact_id: "art_web_fixture_export",
  label: "Public puzzle export",
  media_type: "application/vnd.crosswordai.core-export-bundle+json",
  created_at: fixtureTime,
  href: "/api/artifacts/art_web_fixture_export",
  checksum: "sha256:fixture"
};

export const runDetailFixture: RunDetailResponse = {
  run: {
    run_id: "run_web_fixture",
    run_type: "hardened_core_path",
    status: "succeeded",
    theme: "Miles Davis",
    created_at: fixtureTime,
    completed_at: fixtureTime,
    source_pack_id: "sp_web_fixture",
    puzzle_id: "puzzle_web_fixture",
    artifact_count: 3
  },
  stages: [
    {
      stage_id: "source_pack",
      label: "Source pack",
      status: "succeeded",
      started_at: fixtureTime,
      completed_at: fixtureTime,
      failures: [],
      artifact_ids: ["art_source"]
    }
  ],
  artifacts: [artifactFixture],
  qa_summary: { passed: true, hard_gate_failures: [], soft_score: 0.95 },
  links: { player: "/puzzles/puzzle_web_fixture" }
};

export const runListFixture: RunListResponse = {
  runs: [runDetailFixture.run]
};

export const sourcePackFixture: SourcePackResponse = {
  source_pack_id: "sp_web_fixture",
  theme: "Miles Davis",
  taxonomy: "music_artist",
  taxonomy_confidence: 0.94,
  quality_score: 0.91,
  document_count: 2,
  evidence_snippet_count: 4,
  rights_status: "reviewed_low_risk",
  evidence_previews: [
    {
      evidence_id: "ev_kind_of_blue",
      source_title: "Curated notes",
      snippet_preview: "Kind of Blue is represented as a source-supported album reference.",
      rights_risk: "low"
    }
  ],
  vector_notes: { strategy: "hybrid", top_k: 8, coverage: 0.88 },
  graph_summary: { entity_count: 4, relationship_count: 3 }
};

export const sourcePackBuildFixture: SourcePackBuildResponse = {
  run: runDetailFixture.run,
  source_pack: sourcePackFixture,
  artifact: artifactFixture
};

export const playerPuzzleFixture: PlayerPuzzleResponse = {
  puzzle_id: "puzzle_web_fixture",
  title: "Miles Davis Mini",
  theme: "Miles Davis",
  status: "playable",
  grid: {
    width: 5,
    height: 5,
    rows: ["ABCDE", "FGHIJ", "KLMNO", "PQRST", "UVWXY"]
  },
  clues: [
    {
      clue_id: "clue_001",
      number: 1,
      direction: "across",
      row: 0,
      col: 0,
      answer_length: 5,
      clue_text: "Theme-supported entry from the generated grid",
      difficulty: "easy",
      answer_hash: "f0393febc2f11b59",
      source_evidence_ids: ["ev_kind_of_blue"]
    }
  ],
  metadata: {
    difficulty: "easy",
    source_pack_id: "sp_web_fixture",
    run_id: "run_web_fixture",
    created_at: fixtureTime
  },
  export_policy: {
    public_safe: true,
    raw_evidence_quotes_included: false,
    answer_key_included: false
  }
};

export const registryIndexFixture: RegistryIndexResponse = {
  registries: {
    models: { "mock-local": "1" },
    routes: { "baseline-local": "1" }
  },
  warnings: []
};

export const batchSummaryFixture: BatchSummaryResponse = {
  batch_id: "batch_web_fixture",
  status: "succeeded",
  created_at: fixtureTime,
  routes: ["baseline-local", "cheap-first-cascade"],
  theme_count: 2,
  summary: { succeeded: 2, failed: 0, quarantined: 0, estimated_cost: 0 },
  artifacts: [artifactFixture]
};

export const reportSummaryFixture: ReportSummaryResponse = {
  run_id: "run_web_fixture",
  puzzle_id: "puzzle_web_fixture",
  source_coverage: { source_diversity: 2, retrieval_precision: 0.9, coverage_gaps: [] },
  model_contribution: { "baseline-local:local-template": { clue_count: 2, estimated_cost: 0 } },
  qa_scorecard: { passed: true, soft_score: 0.95, hard_gate_failures: [] },
  links: { inspection_bundle: "/api/reports/run_web_fixture" }
};
