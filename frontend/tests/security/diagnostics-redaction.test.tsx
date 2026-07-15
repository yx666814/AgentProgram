import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { DiagnosticsPage } from "../../src/features/diagnostics/diagnostics-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { auditEvent, toolCallList } from "../support/settings-diagnostics-fixtures";

it("does not render arbitrary event or ToolCall result content", async () => {
  const user = userEvent.setup();
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "health_api_v1_health_get": return reply(request, { status: "ok" });
        case "readiness_api_v1_readiness_get": return reply(request, { status: "ready", database: "ready" });
        case "system_info_api_v1_system_info_get": return reply(request, { backend_version: "0.1.0", protocol_version: 1 });
        case "list_recoveries_api_v1_recovery_get": return reply(request, { recoveries: [] });
        case "replay_events_api_v1_events_replay_get": return reply(request, { events: [auditEvent({ api_key: "raw-key-should-never-render", source_code: "private-source-value", full_chat: "private-chat-value" })] });
        case "list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get": return reply(request, toolCallList({ output: "private-tool-result-value", token: "private-token-value" }));
        default: throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
  });

  render(<BackendProvider port={port}><DiagnosticsPage /></BackendProvider>);
  await user.type(await screen.findByLabelText("Workflow ID"), "workflow_demo");
  await user.click(screen.getByRole("button", { name: "读取审计" }));
  await screen.findByText("workflow.paused");

  expect(screen.queryByText("raw-key-should-never-render")).not.toBeInTheDocument();
  expect(screen.queryByText("private-source-value")).not.toBeInTheDocument();
  expect(screen.queryByText("private-chat-value")).not.toBeInTheDocument();
  expect(screen.queryByText("private-tool-result-value")).not.toBeInTheDocument();
  expect(screen.queryByText("private-token-value")).not.toBeInTheDocument();
  expect(port.calls.commands).toHaveLength(0);
});
