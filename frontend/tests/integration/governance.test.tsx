import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { ApprovalsPage } from "../../src/features/approvals/approvals-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { approvalFixture, gateFixture, governanceScope } from "../support/governance-fixtures";

it("sends a MANUAL warning decision and waits for approval.decided", async () => {
  const user = userEvent.setup();
  const scope = governanceScope("manual");
  const gate = gateFixture("warning", "pending");
  let approval = approvalFixture("pending");
  const port = createFakeDesktopPort({
    query(request) {
      switch (request.operationId) {
        case "get_project_api_v1_projects__project_id__get": return reply(request, scope.project);
        case "list_workflows_api_v1_projects__project_id__workflows_get": return reply(request, { workflows: [scope.workflow.workflow] });
        case "get_workflow_api_v1_workflows__workflow_id__get": return reply(request, scope.workflow);
        case "list_approvals_api_v1_workflows__workflow_id__approvals_get": return reply(request, { approvals: [approval] });
        case "list_capability_requests_api_v1_workflows__workflow_id__capability_requests_get": return reply(request, { requests: [] });
        case "list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get": return reply(request, { gates: [gate] });
        default: throw new Error(`Unexpected query ${request.operationId}`);
      }
    },
    command(request) {
      if (request.operationId !== "decide_gate_approval_api_v1_approvals__approval_id__decision_post") {
        throw new Error(`Unexpected command ${request.operationId}`);
      }
      approval = approvalFixture("approved");
      return reply(request, { approval, gate: { ...gate, resolution: "approved" }, handoff: null, change_request: null });
    },
  });

  render(<BackendProvider port={port}><MemoryRouter initialEntries={["/projects/project_demo/approvals"]}><Routes><Route path="/projects/:projectId/approvals" element={<ApprovalsPage />} /></Routes></MemoryRouter></BackendProvider>);
  await user.click(await screen.findByRole("button", { name: "批准" }));
  expect(screen.getByText(/等待 approval\.decided/)).toBeVisible();
  expect(port.calls.commands[0]?.payload).toMatchObject({ approved: true, expected_version: 1 });
  port.emit({ schema_version: 1, event_id: 20, event_type: "approval.decided", correlation_id: "correlation_approval", actor: { type: "user", id: "user_local" }, source: "backend", occurred_at: "2026-07-15T08:01:00Z", project_id: "project_demo", workflow_id: "workflow_demo", payload: { approval_id: "approval_demo", target_id: "gate_demo", status: "approved" } });
  expect(await screen.findByText("approved")).toBeVisible();
});
