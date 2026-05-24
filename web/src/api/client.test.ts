import { CrosswordApiClient, ApiClientError } from "./client";
import { healthFixture, playerPuzzleFixture, runDetailFixture, runListFixture, sourcePackBuildFixture } from "./fixtures";
import { createMockFetch } from "./mockTransport";

describe("CrosswordApiClient", () => {
  it("returns typed health payloads", async () => {
    const fetchImpl = createMockFetch([{ path: "/health", body: healthFixture }]);
    const client = new CrosswordApiClient({ fetchImpl });

    await expect(client.health()).resolves.toEqual(healthFixture);
    expect(fetchImpl.calls).toEqual([{ method: "GET", path: "/health", body: undefined }]);
  });

  it("posts source-pack and generation requests with JSON bodies", async () => {
    const fetchImpl = createMockFetch([
      { method: "POST", path: "/api/source-packs", body: sourcePackBuildFixture },
      { method: "POST", path: "/api/puzzles/generate", body: runDetailFixture }
    ]);
    const client = new CrosswordApiClient({ fetchImpl });

    await expect(client.createSourcePack({ theme: "Miles Davis", notes: "Kind of Blue" })).resolves.toEqual(
      sourcePackBuildFixture
    );
    await expect(client.generatePuzzle({ theme: "Miles Davis", notes: "Kind of Blue" })).resolves.toEqual(
      runDetailFixture
    );
    expect(fetchImpl.calls).toEqual([
      {
        method: "POST",
        path: "/api/source-packs",
        body: JSON.stringify({ theme: "Miles Davis", notes: "Kind of Blue" })
      },
      {
        method: "POST",
        path: "/api/puzzles/generate",
        body: JSON.stringify({ theme: "Miles Davis", notes: "Kind of Blue" })
      }
    ]);
  });

  it("lists generation runs", async () => {
    const fetchImpl = createMockFetch([{ path: "/api/runs", body: runListFixture }]);
    const client = new CrosswordApiClient({ fetchImpl });

    await expect(client.listRuns()).resolves.toEqual(runListFixture);
  });

  it("normalizes structured API errors", async () => {
    const fetchImpl = createMockFetch([
      {
        path: "/api/puzzles/missing",
        status: 404,
        headers: { "x-correlation-id": "corr_missing" },
        body: {
          error: {
            code: "not_found",
            message: "Puzzle not found.",
            details: { puzzle_id: "missing" },
            remediation: "Check the puzzle ID."
          },
          correlation_id: "corr_missing"
        }
      }
    ]);
    const client = new CrosswordApiClient({ fetchImpl });

    await expect(client.getPlayerPuzzle("missing")).rejects.toMatchObject({
      code: "not_found",
      status: 404,
      correlationId: "corr_missing",
      remediation: "Check the puzzle ID."
    });
  });

  it("retries safe reads on retryable HTTP statuses", async () => {
    const fetchImpl = createMockFetch([
      { path: "/api/puzzles/puzzle_web_fixture", status: 503, body: { error: "retry" } },
      { path: "/api/puzzles/puzzle_web_fixture", body: playerPuzzleFixture }
    ]);
    const client = new CrosswordApiClient({ fetchImpl, retries: 1 });

    await expect(client.getPlayerPuzzle("puzzle_web_fixture")).resolves.toEqual(playerPuzzleFixture);
    expect(fetchImpl.calls).toHaveLength(2);
  });

  it("converts aborts into timeout errors", async () => {
    const fetchImpl = ((_input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
        });
      })) as typeof fetch;
    const client = new CrosswordApiClient({ fetchImpl, timeoutMs: 1, retries: 0 });

    await expect(client.health()).rejects.toMatchObject({
      code: "request_timeout"
    });
  });

  it("normalizes malformed error responses", async () => {
    const fetchImpl = (async () => new Response("not-json", { status: 500 })) as typeof fetch;
    const client = new CrosswordApiClient({ fetchImpl, retries: 0 });

    await expect(client.health()).rejects.toBeInstanceOf(ApiClientError);
    await expect(client.health()).rejects.toMatchObject({
      code: "http_error",
      status: 500
    });
  });
});
