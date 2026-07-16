import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { DiagnosticsPage } from "../../src/features/diagnostics/diagnostics-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { auditEvent, recoveryRecord, toolCallList } from "../support/settings-diagnostics-fixtures";

it("loads real system, event replay, ToolCall and recovery contracts", async () => {
  const user = userEvent.setup();
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "health_api_v1_health_get": return reply(request, { status: "ok" });
        case "readiness_api_v1_readiness_get": return reply(request, { status: "ready", database: "ready" });
        case "system_info_api_v1_system_info_get": return reply(request, { backend_version: "0.1.0", protocol_version: 1 });
        case "list_recoveries_api_v1_recovery_get": return reply(request, { recoveries: [recoveryRecord()] });
        case "replay_events_api_v1_events_replay_get": return reply(request, { events: [auditEvent()] });
        case "list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get": return reply(request, toolCallList());
        default: throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
  });

  render(<BackendProvider port={port}><DiagnosticsPage /></BackendProvider>);
  await user.type(await screen.findByLabelText("Workflow ID"), "workflow_demo");
  await user.clear(screen.getByLabelText("after_event_id"));
  await user.type(screen.getByLabelText("after_event_id"), "41");
  await user.click(screen.getByRole("button", { name: "读取审计" }));

  expect(await screen.findByText("workflow.paused")).toBeVisible();
  expect(screen.getByText("Read")).toBeVisible();
  expect(screen.getByText("recovery_demo")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "导出诊断包" }));
  expect(port.calls.diagnosticsExports).toEqual([
    { workflowId: "workflow_demo", afterEventId: 41 },
  ]);
  expect(await screen.findByText(/脱敏诊断包已导出到/)).toBeVisible();
  const replay = port.calls.queries.find((request) => request.operationId === "replay_events_api_v1_events_replay_get");
  expect(replay?.parameters).toEqual({ query: { workflow_id: "workflow_demo", after_event_id: 41 } });
});
