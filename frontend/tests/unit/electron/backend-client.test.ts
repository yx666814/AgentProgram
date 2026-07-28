// @vitest-environment node

import { afterEach, expect, it, vi } from "vitest";

import { BackendClient } from "../../../electron/backend-client";
import { LocalPathPolicy } from "../../../electron/local-path-policy";
import type { OperationMap } from "../../../electron/runtime-contracts";
import type { SidecarManager } from "../../../electron/sidecar";

const operations: OperationMap = Object.freeze({
  orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post: {
    method: "POST",
    path: "/api/v1/workflows/{workflow_id}/orchestration/stream",
  },
  stream_agent_run_api_v1_agent_runs__run_id__stream_post: {
    method: "POST",
    path: "/api/v1/agent-runs/{run_id}/stream",
  },
  stream_run: { method: "POST", path: "/api/v1/agent-runs/{run_id}/stream" },
  read_output: { method: "GET", path: "/api/v1/agent-runs/{run_id}/output" },
});

it("forwards NDJSON frames incrementally through the dedicated stream channel", async () => {
  const encoder = new TextEncoder();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode('{"type":"chunk","text":"hel'));
              controller.enqueue(encoder.encode('lo"}\n{"type":"run_completed","status":"succeeded"}\n'));
              controller.close();
            },
          }),
          {
            headers: { "Content-Type": "application/x-ndjson; charset=utf-8" },
            status: 200,
          },
        ),
      ),
    ),
  );
  const frames: unknown[] = [];

  const reply = await client().executeStream(
    {
      operationId: "stream_agent_run_api_v1_agent_runs__run_id__stream_post",
      requestId: "stream-request",
      parameters: { path: { run_id: "agentrun_1" } },
      payload: { instruction: "run", correlation_id: "00000000-0000-4000-8000-000000000000" },
    },
    (frame) => { frames.push(frame); },
  );

  expect(reply).toEqual({ requestId: "stream-request", statusCode: 200, payload: null });
  expect(frames).toEqual([
    { type: "chunk", text: "hello" },
    { type: "run_completed", status: "succeeded" },
  ]);
});

function client(): BackendClient {
  const sidecar = {
    connection: () =>
      Promise.resolve({
        host: "127.0.0.1",
        origin: "http://127.0.0.1:54321",
        pid: 123,
        port: 54321,
        sessionToken: "temporary-session-token",
      }),
  } as unknown as SidecarManager;
  return new BackendClient(sidecar, operations, new LocalPathPolicy());
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("parses bounded NDJSON stream frames through the command channel", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response('{"type":"delta","text":"hello"}\n{"type":"done"}\n', {
          headers: { "Content-Type": "application/x-ndjson; charset=utf-8" },
          status: 200,
        }),
      ),
    ),
  );

  const reply = await client().execute(
    {
      operationId: "stream_run",
      requestId: "stream-request",
      parameters: { path: { run_id: "agentrun_1" } },
      payload: { instruction: "run" },
    },
    "command",
  );

  expect(reply.statusCode).toBe(200);
  expect(reply.payload).toEqual([
    { type: "delta", text: "hello" },
    { type: "done" },
  ]);
});

it("preserves plain-text agent output without attempting JSON parsing", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response("final model output", {
          headers: { "Content-Type": "text/plain; charset=utf-8" },
          status: 200,
        }),
      ),
    ),
  );

  const reply = await client().execute(
    {
      operationId: "read_output",
      requestId: "output-request",
      parameters: { path: { run_id: "agentrun_1" } },
    },
    "query",
  );

  expect(reply.statusCode).toBe(200);
  expect(reply.payload).toBe("final model output");
});
