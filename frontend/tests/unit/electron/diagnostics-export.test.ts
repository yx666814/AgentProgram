// @vitest-environment node

import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { afterEach, expect, it } from "vitest";

import type { BackendClient } from "../../../electron/backend-client";
import { DiagnosticsExporter } from "../../../electron/diagnostics-export";
import type { SidecarManager } from "../../../electron/sidecar";

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

it("writes a safe diagnostic projection without event payloads, tool results or secrets", async () => {
  const root = join(tmpdir(), `xingxie-diagnostics-${randomUUID()}`);
  roots.push(root);
  await mkdir(root, { recursive: true });
  const sums = join(root, "SHA256SUMS.json");
  const output = join(root, "diagnostics.json");
  await writeFile(sums, JSON.stringify({ files: { "openapi.json": "HASH" } }), "utf8");
  const backend = {
    executeInternal(operationId: string) {
      const payloads: Record<string, unknown> = {
        system_info_api_v1_system_info_get: { backend_version: "0.1.0", protocol_version: 1 },
        readiness_api_v1_readiness_get: { status: "ready", database: "ready" },
        list_recoveries_api_v1_recovery_get: { recoveries: [] },
        replay_events_api_v1_events_replay_get: {
          events: [
            {
              schema_version: 1,
              event_id: 1,
              event_type: "workflow.paused",
              source: "backend",
              correlation_id: "correlation",
              occurred_at: "2026-07-15T00:00:00Z",
              payload: { status: "paused", api_key: "raw-secret", source_code: "private" },
            },
          ],
        },
        list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get: {
          calls: [
            {
              id: "toolcall_1",
              tool_name: "Read",
              capability: "read_project_files",
              arguments_hash: "hash",
              status: "succeeded",
              result: { output: "private-tool-result" },
            },
          ],
        },
      };
      return Promise.resolve({ requestId: "request", statusCode: 200, payload: payloads[operationId] });
    },
  } as BackendClient;
  const sidecar = {
    publicState: () => Promise.resolve({ host: "127.0.0.1", port: 54321, pid: 1234, status: "ready" as const }),
    diagnostics: () => ['{"authorization":"Bearer top-secret"}', "sk-private-secret"],
  } as unknown as SidecarManager;

  await new DiagnosticsExporter(backend, sidecar, sums).write(output, {
    workflowId: "workflow_demo",
    afterEventId: 0,
  });

  const content = await readFile(output, "utf8");
  expect(content).toContain("workflow.paused");
  expect(content).not.toContain("private-tool-result");
  expect(content).not.toContain("raw-secret");
  expect(content).not.toContain("source_code");
  expect(content).not.toContain("top-secret");
  expect(content).not.toContain("sk-private-secret");
  expect(content).toContain("[REDACTED]");
});
