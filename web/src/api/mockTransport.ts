import type { FetchLike } from "./client";

export interface MockRoute {
  method?: string;
  path: string;
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export type MockFetch = FetchLike & {
  calls: Array<{ method: string; path: string; body: string | undefined }>;
};

export function createMockFetch(routes: MockRoute[]): MockFetch {
  const remaining = [...routes];
  const calls: MockFetch["calls"] = [];

  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(input.toString(), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ method, path: url.pathname, body: init?.body?.toString() });

    const routeIndex = remaining.findIndex(
      (route) => route.path === url.pathname && (route.method ?? "GET").toUpperCase() === method
    );

    if (routeIndex === -1) {
      return jsonResponse(
        {
          error: {
            code: "not_found",
            message: `No mock route for ${method} ${url.pathname}.`,
            details: {},
            remediation: "Add the route to createMockFetch."
          },
          correlation_id: "corr_mock_missing"
        },
        404,
        { "x-correlation-id": "corr_mock_missing" }
      );
    }

    const [route] = remaining.splice(routeIndex, 1);
    return jsonResponse(route.body ?? {}, route.status ?? 200, route.headers);
  }) as MockFetch;

  fetchImpl.calls = calls;
  return fetchImpl;
}

function jsonResponse(body: unknown, status: number, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json",
      ...headers
    }
  });
}
