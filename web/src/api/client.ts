import type {
  ApiErrorResponse,
  BatchSummaryResponse,
  GeneratePuzzleRequest,
  HealthResponse,
  PlayerPuzzleResponse,
  RegistryIndexResponse,
  ReportSummaryResponse,
  RunDetailResponse,
  RunListResponse,
  SourcePackBuildRequest,
  SourcePackBuildResponse,
  SourcePackResponse
} from "./types";

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
  retries?: number;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
  retries?: number;
}

export class ApiClientError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly remediation: string | null;
  readonly correlationId: string | null;

  constructor(args: {
    message: string;
    code: string;
    status?: number | null;
    details?: Record<string, unknown>;
    remediation?: string | null;
    correlationId?: string | null;
    cause?: unknown;
  }) {
    super(args.message, { cause: args.cause });
    this.name = "ApiClientError";
    this.status = args.status ?? null;
    this.code = args.code;
    this.details = args.details ?? {};
    this.remediation = args.remediation ?? null;
    this.correlationId = args.correlationId ?? null;
  }
}

export class CrosswordApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;
  private readonly timeoutMs: number;
  private readonly retries: number;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.retries = options.retries ?? 1;
  }

  health(options?: RequestOptions): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health", options);
  }

  createSourcePack(payload: SourcePackBuildRequest, options?: RequestOptions): Promise<SourcePackBuildResponse> {
    return this.request<SourcePackBuildResponse>("/api/source-packs", {
      ...options,
      method: "POST",
      body: payload
    });
  }

  getSourcePack(sourcePackId: string, options?: RequestOptions): Promise<SourcePackResponse> {
    return this.request<SourcePackResponse>(`/api/source-packs/${encodeURIComponent(sourcePackId)}`, options);
  }

  generatePuzzle(payload: GeneratePuzzleRequest, options?: RequestOptions): Promise<RunDetailResponse> {
    return this.request<RunDetailResponse>("/api/puzzles/generate", {
      ...options,
      method: "POST",
      body: payload
    });
  }

  listRuns(options?: RequestOptions): Promise<RunListResponse> {
    return this.request<RunListResponse>("/api/runs", options);
  }

  getRun(runId: string, options?: RequestOptions): Promise<RunDetailResponse> {
    return this.request<RunDetailResponse>(`/api/runs/${encodeURIComponent(runId)}`, options);
  }

  getPlayerPuzzle(puzzleId: string, options?: RequestOptions): Promise<PlayerPuzzleResponse> {
    return this.request<PlayerPuzzleResponse>(`/api/puzzles/${encodeURIComponent(puzzleId)}`, options);
  }

  getRegistries(options?: RequestOptions): Promise<RegistryIndexResponse> {
    return this.request<RegistryIndexResponse>("/api/registries", options);
  }

  getBatch(batchId: string, options?: RequestOptions): Promise<BatchSummaryResponse> {
    return this.request<BatchSummaryResponse>(`/api/batches/${encodeURIComponent(batchId)}`, options);
  }

  getReport(runId: string, options?: RequestOptions): Promise<ReportSummaryResponse> {
    return this.request<ReportSummaryResponse>(`/api/reports/${encodeURIComponent(runId)}`, options);
  }

  getArtifact<T = unknown>(artifactId: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(`/api/artifacts/${encodeURIComponent(artifactId)}`, options);
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = (options.method ?? "GET").toUpperCase();
    const attempts = Math.max(0, options.retries ?? this.retries) + 1;
    const safeToRetry = method === "GET" || method === "HEAD";
    let lastError: unknown;

    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        const response = await this.fetchWithTimeout(path, method, options);
        if (response.ok) {
          return (await response.json()) as T;
        }
        if (safeToRetry && attempt < attempts && isRetryableStatus(response.status)) {
          continue;
        }
        throw await errorFromResponse(response);
      } catch (error) {
        lastError = error;
        if (error instanceof ApiClientError) {
          throw error;
        }
        if (!safeToRetry || attempt >= attempts || isAbortError(error)) {
          throw networkError(error);
        }
      }
    }

    throw networkError(lastError);
  }

  private async fetchWithTimeout(path: string, method: string, options: RequestOptions): Promise<Response> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs ?? this.timeoutMs);
    const headers = new Headers(options.headers);
    if (options.body !== undefined && !headers.has("content-type")) {
      headers.set("content-type", "application/json");
    }

    try {
      return await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal
      });
    } finally {
      window.clearTimeout(timeout);
    }
  }
}

export const apiClient = new CrosswordApiClient();

async function errorFromResponse(response: Response): Promise<ApiClientError> {
  const correlationId = response.headers.get("x-correlation-id");
  let payload: ApiErrorResponse | null = null;
  try {
    payload = (await response.json()) as ApiErrorResponse;
  } catch {
    payload = null;
  }

  if (payload?.error) {
    return new ApiClientError({
      status: response.status,
      code: payload.error.code,
      message: payload.error.message,
      details: payload.error.details,
      remediation: payload.error.remediation,
      correlationId: payload.correlation_id ?? correlationId
    });
  }

  return new ApiClientError({
    status: response.status,
    code: "http_error",
    message: `Request failed with HTTP ${response.status}.`,
    correlationId
  });
}

function networkError(error: unknown): ApiClientError {
  if (isAbortError(error)) {
    return new ApiClientError({
      code: "request_timeout",
      message: "The request timed out.",
      cause: error
    });
  }
  return new ApiClientError({
    code: "network_error",
    message: "The request could not be completed.",
    cause: error
  });
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
}

function isRetryableStatus(status: number): boolean {
  return status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
}
