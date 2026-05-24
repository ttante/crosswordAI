export type JsonObject = Record<string, unknown>;

export interface ApiErrorPayload {
  code: string;
  message: string;
  details: JsonObject;
  remediation: string | null;
}

export interface ApiErrorResponse {
  error: ApiErrorPayload;
  correlation_id: string;
}

export interface HealthResponse {
  service: "crosswordai-web";
  version: string;
  status: "ok" | "degraded";
  correlation_id: string;
  dependencies: JsonObject;
}

export interface ArtifactSummary {
  artifact_id: string;
  label: string;
  media_type: string;
  created_at: string;
  href: string | null;
  checksum: string | null;
}

export type RunStatus = "running" | "succeeded" | "failed" | "quarantined";
export type StageStatus = "pending" | "running" | "succeeded" | "failed" | "quarantined" | "skipped";
export type Direction = "across" | "down";

export interface RunSummary {
  run_id: string;
  run_type: string;
  status: RunStatus;
  theme: string;
  created_at: string;
  completed_at: string | null;
  source_pack_id: string | null;
  puzzle_id: string | null;
  artifact_count: number;
}

export interface RunStage {
  stage_id: string;
  label: string;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
  failures: string[];
  artifact_ids: string[];
}

export interface RunDetailResponse {
  run: RunSummary;
  stages: RunStage[];
  artifacts: ArtifactSummary[];
  qa_summary: JsonObject;
  links: JsonObject;
}

export interface RunListResponse {
  runs: RunSummary[];
}

export interface SourcePackResponse {
  source_pack_id: string;
  theme: string;
  taxonomy: string;
  taxonomy_confidence: number;
  quality_score: number;
  document_count: number;
  evidence_snippet_count: number;
  rights_status: string;
  evidence_previews: JsonObject[];
  vector_notes: JsonObject;
  graph_summary: JsonObject;
}

export interface SourcePackBuildResponse {
  run: RunSummary;
  source_pack: SourcePackResponse;
  artifact: ArtifactSummary;
}

export interface GeneratePuzzleRequest {
  theme: string;
  notes: string;
  route_id?: string;
  puzzle_id?: string;
  grid_size?: number;
  clue_styles?: string[];
  candidate_limit?: number;
}

export interface SourcePackBuildRequest {
  theme: string;
  notes: string;
}

export interface PlayerGrid {
  width: number;
  height: number;
  rows: string[];
}

export interface PlayerClue {
  clue_id: string;
  number: number;
  direction: Direction;
  row: number;
  col: number;
  answer_length: number;
  clue_text: string;
  difficulty: string;
  answer_hash: string;
  source_evidence_ids: string[];
}

export interface PlayerPuzzleResponse {
  puzzle_id: string;
  title: string;
  theme: string;
  status: "playable" | "quarantined";
  grid: PlayerGrid;
  clues: PlayerClue[];
  metadata: JsonObject;
  export_policy: JsonObject;
}

export interface RegistryIndexResponse {
  registries: Record<string, Record<string, string>>;
  warnings: string[];
}

export interface BatchSummaryResponse {
  batch_id: string;
  status: StageStatus;
  created_at: string;
  routes: string[];
  theme_count: number;
  summary: JsonObject;
  artifacts: ArtifactSummary[];
}

export interface ReportSummaryResponse {
  run_id: string;
  puzzle_id: string;
  source_coverage: JsonObject;
  model_contribution: JsonObject;
  qa_scorecard: JsonObject;
  links: JsonObject;
}
