import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";

import { BackendProvider } from "../../src/api/backend-context";
import { ArtifactsPage } from "../../src/features/artifacts/artifacts-page";
import { createFakeDesktopPort, reply } from "../support/fake-desktop-port";
import { artifactInventory, gateFixture, governanceScope, handoffFixture } from "../support/governance-fixtures";

it("marks the completion chain only from committed artifact, gate, policy and handoff records", async () => {
  const scope = governanceScope("autonomous");
  const port = createFakeDesktopPort({ query(request) {
    switch (request.operationId) {
      case "get_project_api_v1_projects__project_id__get": return reply(request, scope.project);
      case "list_workflows_api_v1_projects__project_id__workflows_get": return reply(request, { workflows: [scope.workflow.workflow] });
      case "get_workflow_api_v1_workflows__workflow_id__get": return reply(request, scope.workflow);
      case "list_artifacts_api_v1_workflows__workflow_id__artifacts_get": return reply(request, artifactInventory());
      case "list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get": return reply(request, { gates: [gateFixture("pass", "automatic")] });
      case "list_approvals_api_v1_workflows__workflow_id__approvals_get": return reply(request, { approvals: [] });
      case "list_handoffs_api_v1_workflows__workflow_id__handoffs_get": return reply(request, { handoffs: [handoffFixture()] });
      case "list_change_requests_api_v1_workflows__workflow_id__change_requests_get": return reply(request, { change_requests: [] });
      default: throw new Error(`Unexpected query ${request.operationId}`);
    }
  } });
  const { container } = render(<BackendProvider port={port}><MemoryRouter initialEntries={["/projects/project_demo/artifacts"]}><Routes><Route path="/projects/:projectId/artifacts" element={<ArtifactsPage />} /></Routes></MemoryRouter></BackendProvider>);
  await screen.findByText("PASS · automatic");
  expect(container.querySelectorAll(".completion-chain [data-complete='true']")).toHaveLength(4);
});
