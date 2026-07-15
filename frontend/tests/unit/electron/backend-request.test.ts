// @vitest-environment node

import { expect, it } from "vitest";

import {
  BackendRequestValidationError,
  buildBackendFetchRequest,
} from "../../../electron/backend-request";
import type { OperationMap } from "../../../electron/runtime-contracts";

const operations: OperationMap = Object.freeze({
  read_project: { method: "GET", path: "/api/v1/projects/{project_id}" },
  create_project: { method: "POST", path: "/api/v1/projects" },
});

it("maps a frozen query operation to a loopback request", () => {
  const result = buildBackendFetchRequest({
    request: {
      operationId: "read_project",
      requestId: "request-1",
      parameters: {
        path: { project_id: "project 中文" },
        query: { limit: 20, state: ["open", "closed"] },
      },
    },
    kind: "query",
    operations,
    origin: "http://127.0.0.1:54321",
    sessionToken: "temporary-secret",
    timeoutSignal: AbortSignal.timeout(1_000),
  });

  expect(result.url.origin).toBe("http://127.0.0.1:54321");
  expect(result.url.pathname).toBe("/api/v1/projects/project%20%E4%B8%AD%E6%96%87");
  expect(result.url.searchParams.getAll("state")).toEqual(["open", "closed"]);
  expect(new Headers(result.init.headers).get("authorization")).toBe(
    "Bearer temporary-secret",
  );
  expect(result.init.body).toBeUndefined();
});

it("rejects unknown, mismatched and prototype operation ids", () => {
  for (const [operationId, kind] of [
    ["missing", "query"],
    ["__proto__", "query"],
    ["create_project", "query"],
  ] as const) {
    expect(() =>
      buildBackendFetchRequest({
        request: { operationId, requestId: "request-2" },
        kind,
        operations,
        origin: "http://127.0.0.1:54321",
        sessionToken: "temporary-secret",
        timeoutSignal: AbortSignal.timeout(1_000),
      }),
    ).toThrow(BackendRequestValidationError);
  }
});

it("serializes command payloads without accepting arbitrary parameter groups", () => {
  const result = buildBackendFetchRequest({
    request: {
      operationId: "create_project",
      requestId: "request-3",
      payload: { name: "demo" },
    },
    kind: "command",
    operations,
    origin: "http://127.0.0.1:54321",
    sessionToken: "temporary-secret",
    timeoutSignal: AbortSignal.timeout(1_000),
  });
  expect(result.init.body).toBe('{"name":"demo"}');

  expect(() =>
    buildBackendFetchRequest({
      request: {
        operationId: "create_project",
        requestId: "request-4",
        parameters: { headers: { authorization: "forbidden" } },
      },
      kind: "command",
      operations,
      origin: "http://127.0.0.1:54321",
      sessionToken: "temporary-secret",
      timeoutSignal: AbortSignal.timeout(1_000),
    }),
  ).toThrow("unsupported group");
});

