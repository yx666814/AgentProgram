// @vitest-environment node

import { expect, it } from "vitest";

import type { BackendReply, BackendRequest } from "../../electron/desktop-port";
import { ApiClient } from "../../src/api/client";
import type { ApiRequestError } from "../../src/api/errors";
import type { ApiTransport } from "../../src/api/transport";

function transportWithReply(statusCode: number, payload: unknown): ApiTransport {
  const respond = <T>(request: BackendRequest): Promise<BackendReply<T>> =>
    Promise.resolve({ requestId: request.requestId, statusCode, payload: payload as T });
  return {
    query: respond,
    command: respond,
    subscribe: () => () => undefined,
    requestReplay: () => Promise.resolve(),
  };
}

it("uses a frozen operation id without exposing authentication", async () => {
  const client = new ApiClient(transportWithReply(200, { status: "ok" }), () => "request-1");
  const response = await client.query<{ status: string }>("health_api_v1_health_get");

  expect(response).toEqual({
    operationId: "health_api_v1_health_get",
    requestId: "request-1",
    statusCode: 200,
    payload: { status: "ok" },
  });
  expect(response).not.toHaveProperty("token");
});

it("keeps the current version from the backend conflict envelope", async () => {
  const client = new ApiClient(
    transportWithReply(409, {
      error: {
        code: "project.version_conflict",
        message: "Project version changed",
        retryable: false,
        details: { actual_version: 7 },
      },
    }),
    () => "request-2",
  );

  await expect(
    client.command("close_project_api_v1_projects__project_id__close_post", {
      correlationId: "correlation-2",
    }),
  ).rejects.toMatchObject({
    code: "project.version_conflict",
    correlationId: "correlation-2",
    currentVersion: "7",
  } satisfies Partial<ApiRequestError>);
});

it("preserves pagination parameters and an idempotency key across an explicit retry", async () => {
  const requests: BackendRequest[] = [];
  const transport = transportWithReply(200, { projects: [] });
  const recordingTransport: ApiTransport = {
    ...transport,
    query: <T>(request: BackendRequest): Promise<BackendReply<T>> => {
      requests.push(request);
      return transport.query<T>(request);
    },
    command: <T>(request: BackendRequest): Promise<BackendReply<T>> => {
      requests.push(request);
      return transport.command<T>(request);
    },
  };
  const client = new ApiClient(recordingTransport, () => "generated-request");
  await client.query("list_projects_api_v1_projects_get", {
    parameters: { cursor: "page-2" },
  });
  const retry = {
    requestId: "command-retry-1",
    correlationId: "correlation-retry-1",
    payload: { idempotency_key: "stable-idempotency-key-0001" },
  };
  await client.command("execute_tool_api_v1_tasks__task_id__tool_calls_post", retry);
  await client.command("execute_tool_api_v1_tasks__task_id__tool_calls_post", retry);

  expect(requests[0]?.parameters).toEqual({ cursor: "page-2" });
  expect(requests[1]?.payload).toEqual(requests[2]?.payload);
  expect(requests[1]?.requestId).toBe("command-retry-1");
  expect(requests[2]?.requestId).toBe("command-retry-1");
});
