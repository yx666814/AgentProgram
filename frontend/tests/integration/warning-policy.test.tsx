import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { ApprovalsPage } from "../../src/features/approvals/approvals-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { gateFixture, governanceScope } from "../support/governance-fixtures";

it("does not expose a manual approval shortcut for AUTONOMOUS warning_blocked", async () => {
  const scope = governanceScope("autonomous");
  const port = createFakeDesktopPort({ query(request) {
    switch (request.operationId) {
      case "get_project_api_v1_projects__project_id__get": return reply(request, scope.project);
      case "list_workflows_api_v1_projects__project_id__workflows_get": return reply(request, { workflows: [scope.workflow.workflow] });
      case "get_workflow_api_v1_workflows__workflow_id__get": return reply(request, scope.workflow);
      case "list_approvals_api_v1_workflows__workflow_id__approvals_get": return reply(request, { approvals: [] });
      case "list_capability_requests_api_v1_workflows__workflow_id__capability_requests_get": return reply(request, { requests: [] });
      case "list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get": return reply(request, { gates: [gateFixture("warning", "pending")] });
      default: throw new Error(`Unexpected query ${request.operationId}`);
    }
  } });
  render(<BackendProvider port={port}><MemoryRouter initialEntries={["/projects/project_demo/approvals"]}><Routes><Route path="/projects/:projectId/approvals" element={<ApprovalsPage />} /></Routes></MemoryRouter></BackendProvider>);
  expect(await screen.findByText(/AUTONOMOUS WARNING/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
});
